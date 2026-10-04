#!/usr/bin/env python3
"""Managed Frappe Socket.IO reverse-proxy editing for nginx server blocks.

Inserts, replaces, or removes a single managed ``location /socket.io`` block
inside an nginx ``server`` block. Browser-hosted frontends served from a domain
different from the Frappe backend use this proxy so the browser can reach
Frappe's Socket.IO endpoint on the frontend's own origin (avoiding cross-origin
rejections) while the upstream Host/Origin/X-Frappe-Site-Name still identify the
Frappe site.

The managed region is delimited by marker comments, so repeated runs are
idempotent: existing managed regions are stripped before the block is
re-inserted, and a strip is the exact inverse of an insert. A pre-existing
unmanaged ``location /socket.io`` in the target block is adopted and replaced so
the tool can be rolled out over hand-written configurations without creating a
duplicate location.

Reads nginx configuration on stdin and writes the result to stdout.

Usage:
    socketio_proxy_config.py apply --backend-host masarbackend.conceptiqs.com \
        [--server-name masaradmin.conceptiqs.com] [--backend-scheme https] \
        [--socket-target http://127.0.0.1:9000]
    socketio_proxy_config.py remove
    socketio_proxy_config.py check
"""

from __future__ import annotations

import argparse
import re
import sys

BEGIN_MARKER = "# >>> frappe socket.io proxy (managed) >>>"
END_MARKER = "# <<< frappe socket.io proxy (managed) <<<"

MANAGED_RE = re.compile(
    r"(?ms)^[ \t]*" + re.escape(BEGIN_MARKER) + r".*?^[ \t]*" + re.escape(END_MARKER) + r"[ \t]*\n"
)

SERVER_NAME_RE = re.compile(r"server_name\s+([^;]+);")
LISTEN_443_RE = re.compile(r"\blisten\b[^;]*\b443\b")
CONTENT_LOCATION_RE = re.compile(r"\blocation\s+/")
REDIRECT_RE = re.compile(r"\breturn\s+(?:30[0-9]|444)\b")
DIRECTIVE_BEFORE_BRACE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*$")
SOCKETIO_LOCATION_RE = re.compile(r"\blocation\b\s+(?:[=~^*]+\s+)?/socket\.io\b")


class ServerBlock:
    """A parsed ``server { ... }`` span with the attributes used for targeting."""

    def __init__(self, text: str, open_index: int, close_index: int) -> None:
        self.open_index = open_index
        self.close_index = close_index
        self.body = text[open_index + 1 : close_index]
        self.names: list[str] = []
        for match in SERVER_NAME_RE.findall(self.body):
            self.names.extend(match.split())
        self.listens_443 = bool(LISTEN_443_RE.search(self.body))
        self.has_content_location = bool(CONTENT_LOCATION_RE.search(self.body))
        self.is_redirect_only = bool(REDIRECT_RE.search(self.body)) and not self.has_content_location

    def score(self) -> tuple[int, int, int]:
        """Rank content blocks above redirect-only blocks."""
        return (
            0 if self.is_redirect_only else 1,
            1 if self.listens_443 else 0,
            1 if self.has_content_location else 0,
        )


def find_server_blocks(text: str) -> list[ServerBlock]:
    """Return every ``server { ... }`` block found in the configuration text."""
    blocks: list[ServerBlock] = []
    stack: list[tuple[int, bool]] = []
    for index, char in enumerate(text):
        if char == "{":
            directive = DIRECTIVE_BEFORE_BRACE_RE.search(text[:index])
            is_server = bool(directive) and directive.group(1) == "server"
            stack.append((index, is_server))
        elif char == "}":
            if stack:
                open_index, is_server = stack.pop()
                if is_server:
                    blocks.append(ServerBlock(text, open_index, index))
    return blocks


def choose_block(blocks: list[ServerBlock], server_name: str) -> ServerBlock:
    """Pick the server block to modify, preferring real (non-redirect) blocks."""
    if not blocks:
        raise SystemExit("error: no server block found in nginx configuration")

    pool = blocks
    if server_name:
        matched = [block for block in blocks if server_name in block.names]
        if not matched:
            raise SystemExit(f"error: no server block declares server_name {server_name!r}")
        pool = matched

    return max(pool, key=ServerBlock.score)


def build_managed_block(
    indent: str,
    backend_host: str,
    backend_scheme: str,
    socket_target: str,
) -> str:
    """Build the marked ``location /socket.io`` block at the given indentation."""
    inner = indent + "    "
    lines = [
        f"{indent}{BEGIN_MARKER}",
        f"{indent}location /socket.io {{",
        f"{inner}proxy_http_version 1.1;",
        f"{inner}proxy_set_header Upgrade $http_upgrade;",
        f'{inner}proxy_set_header Connection "upgrade";',
        "",
        f"{inner}proxy_set_header Host {backend_host};",
        f"{inner}proxy_set_header X-Frappe-Site-Name {backend_host};",
        f"{inner}proxy_set_header Origin {backend_scheme}://{backend_host};",
        "",
        f"{inner}proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        f"{inner}proxy_set_header X-Forwarded-Proto {backend_scheme};",
        f"{inner}proxy_read_timeout 86400;",
        f"{inner}proxy_send_timeout 86400;",
        "",
        f"{inner}proxy_pass {socket_target}/socket.io;",
        "",
        f"{inner}proxy_hide_header Access-Control-Allow-Origin;",
        f"{inner}add_header Access-Control-Allow-Origin $http_origin always;",
        f"{inner}add_header Access-Control-Allow-Credentials true always;",
        f"{indent}}}",
        f"{indent}{END_MARKER}",
    ]
    return "\n".join(lines) + "\n"


def strip_managed_block(text: str) -> str:
    """Remove every managed region; inverse of :func:`build_managed_block`."""
    return MANAGED_RE.sub("", text)


def _find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def find_existing_socketio_location(text: str, block: ServerBlock) -> tuple[int, int, str] | None:
    """Locate an unmanaged ``location /socket.io`` in ``block``.

    Returns ``(start, end, indent)`` where ``start`` is the line start of the
    location directive, ``end`` is just past its closing brace (and trailing
    newline), and ``indent`` is the location's leading whitespace. Only the chosen
    server block is inspected.
    """
    match = SOCKETIO_LOCATION_RE.search(text, block.open_index, block.close_index)
    if not match:
        return None

    open_brace = text.find("{", match.start(), block.close_index)
    if open_brace == -1:
        return None

    close_brace = _find_matching_brace(text, open_brace)
    if close_brace == -1 or close_brace > block.close_index:
        return None

    start = text.rfind("\n", 0, match.start()) + 1
    indent = text[start : match.start()]
    end = close_brace + 1
    while end < len(text) and text[end] in " \t":
        end += 1
    if end < len(text) and text[end] == "\n":
        end += 1

    return start, end, indent


def _block_indent(text: str, close_index: int) -> str:
    line_start = text.rfind("\n", 0, close_index) + 1
    leading = text[line_start:close_index]
    return leading if leading.strip() == "" else ""


def _first_managed_indent(region: str) -> str:
    first_line = region.split("\n", 1)[0]
    return first_line[: len(first_line) - len(first_line.lstrip(" \t"))]


def apply_managed_block(
    text: str,
    server_name: str,
    backend_host: str,
    backend_scheme: str,
    socket_target: str,
) -> str:
    """Return ``text`` with the managed Socket.IO proxy inserted, replaced, or adopted.

    Position is preserved: an existing managed block is replaced in place, and a
    pre-existing unmanaged ``location /socket.io`` in the target block is adopted
    in place. Only a brand-new proxy is appended before the block's closing brace.
    """
    socket_target = socket_target.rstrip("/")
    matches = list(MANAGED_RE.finditer(text))

    if matches:
        first = matches[0]
        indent = _first_managed_indent(first.group(0))
        result = text
        for extra in reversed(matches[1:]):
            result = result[: extra.start()] + result[extra.end() :]
        first = MANAGED_RE.search(result)
        assert first is not None
        managed = build_managed_block(indent, backend_host, backend_scheme, socket_target)
        return result[: first.start()] + managed + result[first.end() :]

    target = choose_block(find_server_blocks(text), server_name)
    existing = find_existing_socketio_location(text, target)
    if existing is not None:
        start, end, indent = existing
        managed = build_managed_block(indent, backend_host, backend_scheme, socket_target)
        return text[:start] + managed + text[end:]

    close_index = target.close_index
    line_start = text.rfind("\n", 0, close_index) + 1
    location_indent = _block_indent(text, close_index) + "    "
    managed = build_managed_block(location_indent, backend_host, backend_scheme, socket_target)
    return text[:line_start] + managed + text[line_start:]


def has_managed_block(text: str) -> bool:
    return bool(MANAGED_RE.search(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="socketio_proxy_config.py",
        description="Insert, replace, or remove a managed Frappe Socket.IO nginx proxy.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    apply_parser = subparsers.add_parser("apply", help="insert or replace the managed block")
    apply_parser.add_argument("--server-name", default="", help="target server_name (default: best block)")
    apply_parser.add_argument("--backend-host", required=True, help="Frappe backend host for Host/Origin")
    apply_parser.add_argument("--backend-scheme", default="https", help="backend URL scheme (default: https)")
    apply_parser.add_argument(
        "--socket-target", default="http://127.0.0.1:9000", help="Socket.IO upstream base"
    )

    subparsers.add_parser("remove", help="remove the managed block")
    subparsers.add_parser("check", help="print present/absent for the managed block")

    args = parser.parse_args(argv)
    text = sys.stdin.read()

    if args.action == "check":
        print("present" if has_managed_block(text) else "absent")
        return 0

    if args.action == "remove":
        sys.stdout.write(strip_managed_block(text))
        return 0

    sys.stdout.write(
        apply_managed_block(
            text,
            server_name=args.server_name,
            backend_host=args.backend_host,
            backend_scheme=args.backend_scheme,
            socket_target=args.socket_target,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
