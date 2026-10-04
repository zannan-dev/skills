#!/usr/bin/env python3
"""Tests for socketio_proxy_config.py.

Run with:
    PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/test_socketio_proxy_config.py
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("socketio_proxy_config.py")
spec = importlib.util.spec_from_file_location("socketio_proxy_config", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

BACKEND = "masarbackend.conceptiqs.com"
BEGIN_MARKER = module.BEGIN_MARKER
END_MARKER = module.END_MARKER


SINGLE_BLOCK = """\
server {
    listen 80;
    listen [::]:80;
    server_name admin.example.com;

    root /var/www/admin;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    access_log /var/log/nginx/admin.access.log;
    error_log /var/log/nginx/admin.error.log;
}
"""

ADMIN_WITH_REDIRECT = """\
server {
    server_name masaradmin.conceptiqs.com;

    root /var/www/masar_admin;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /socket.io {
        proxy_http_version 1.1;
        proxy_pass http://127.0.0.1:9000/socket.io;
    }

    listen [::]:443 ssl; # managed by Certbot
    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/masaradmin.conceptiqs.com/fullchain.pem;
}

server {
    if ($host = masaradmin.conceptiqs.com) {
        return 301 https://$host$request_uri;
    }

    listen 80;
    listen [::]:80;
    server_name masaradmin.conceptiqs.com;
    return 404;
}
"""


def apply(text: str, server_name: str = "") -> str:
    return module.apply_managed_block(
        text,
        server_name=server_name,
        backend_host=BACKEND,
        backend_scheme="https",
        socket_target="http://127.0.0.1:9000",
    )


class ApplyTests(unittest.TestCase):
    def test_inserts_block_inside_server(self):
        result = apply(SINGLE_BLOCK)
        self.assertIn(BEGIN_MARKER, result)
        self.assertIn(END_MARKER, result)
        self.assertIn("location /socket.io {", result)
        self.assertIn(f"proxy_set_header Host {BACKEND};", result)
        self.assertIn(f"proxy_set_header X-Frappe-Site-Name {BACKEND};", result)
        self.assertIn(f"proxy_set_header Origin https://{BACKEND};", result)
        self.assertIn("proxy_pass http://127.0.0.1:9000/socket.io;", result)
        self.assertIn("add_header Access-Control-Allow-Origin $http_origin always;", result)

    def test_block_is_before_closing_brace(self):
        result = apply(SINGLE_BLOCK)
        self.assertLess(result.index("location /socket.io {"), result.rindex("}"))
        self.assertEqual(result.count("location /socket.io {"), 1)

    def test_idempotent(self):
        once = apply(SINGLE_BLOCK)
        twice = apply(once)
        self.assertEqual(once, twice)

    def test_prefers_non_redirect_block(self):
        result = apply(ADMIN_WITH_REDIRECT, server_name="masaradmin.conceptiqs.com")
        self.assertEqual(result.count("location /socket.io {"), 1)
        # Must land in the 443 content block, not the HTTP redirect stub.
        self.assertLess(result.index("location /socket.io {"), result.index("return 301"))

    def test_preserves_unrelated_lines(self):
        result = apply(SINGLE_BLOCK)
        for original in SINGLE_BLOCK.splitlines():
            self.assertIn(original, result.splitlines())

    def test_unknown_server_name_fails(self):
        with self.assertRaises(SystemExit):
            apply(SINGLE_BLOCK, server_name="missing.example.com")

    def test_adopts_existing_unmanaged_location(self):
        result = apply(ADMIN_WITH_REDIRECT, server_name="masaradmin.conceptiqs.com")
        self.assertEqual(result.count("location /socket.io {"), 1)
        self.assertIn(BEGIN_MARKER, result)
        # The hand-written upstream is replaced by the managed one.
        self.assertIn("proxy_pass http://127.0.0.1:9000/socket.io;", result)
        self.assertIn(f"proxy_set_header X-Frappe-Site-Name {BACKEND};", result)

    def test_adoption_preserves_position(self):
        result = apply(ADMIN_WITH_REDIRECT, server_name="masaradmin.conceptiqs.com")
        # The adopted block stays where the original location was, not at EOF.
        self.assertLess(result.index("location /socket.io {"), result.index("listen [::]:443"))

    def test_idempotent_after_adopting(self):
        once = apply(ADMIN_WITH_REDIRECT, server_name="masaradmin.conceptiqs.com")
        twice = apply(once, server_name="masaradmin.conceptiqs.com")
        self.assertEqual(once, twice)


class RemoveTests(unittest.TestCase):
    def test_remove_restores_original(self):
        applied = apply(SINGLE_BLOCK)
        self.assertEqual(module.strip_managed_block(applied), SINGLE_BLOCK)

    def test_remove_is_noop_without_block(self):
        self.assertEqual(module.strip_managed_block(SINGLE_BLOCK), SINGLE_BLOCK)


class CheckTests(unittest.TestCase):
    def test_check_present_and_absent(self):
        self.assertFalse(module.has_managed_block(SINGLE_BLOCK))
        self.assertTrue(module.has_managed_block(apply(SINGLE_BLOCK)))


if __name__ == "__main__":
    unittest.main()
