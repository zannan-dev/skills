#!/usr/bin/env bash
set -euo pipefail

# Add (or update/remove) a managed Frappe Socket.IO reverse-proxy location in an
# existing nginx server block for a frontend served from a different domain than
# the Frappe backend.
#
# Browser-hosted frontends (Flutter web, etc.) that connect to Frappe realtime
# from their own origin need a `/socket.io` proxy on the frontend host. This keeps
# the browser same-origin while forwarding Host/Origin/X-Frappe-Site-Name so the
# upstream Frappe site check passes.
#
# The block is wrapped in managed markers, so repeated runs update in place and
# --remove cleans up exactly what was inserted.

FRONTEND_DOMAIN="${FRONTEND_DOMAIN:-}"
BACKEND_DOMAIN="${BACKEND_DOMAIN:-}"
SSH_USER="${SSH_USER:-root}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-personal}"
BACKEND_SCHEME="${BACKEND_SCHEME:-https}"
SOCKET_TARGET="${SOCKET_TARGET:-http://127.0.0.1:9000}"
CONFIG_NAME="${CONFIG_NAME:-}"
SERVER_NAME="${SERVER_NAME:-}"
CONFIG_FILE="${CONFIG_FILE:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/socketio_proxy_config.py"

BEGIN_MARKER="# >>> frappe socket.io proxy (managed) >>>"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

usage() {
  cat <<EOF
Usage: $0 --frontend DOMAIN --backend DOMAIN [OPTIONS]

Add a managed /socket.io reverse proxy to an existing nginx server block so a
frontend on a different domain can reach Frappe realtime from its own origin.

Required:
  --frontend DOMAIN       Frontend public host (SSH target and nginx server_name)
  --backend DOMAIN        Frappe backend host (Host / Origin / X-Frappe-Site-Name)

Options:
  --config NAME           nginx site name in sites-available
                          (default: auto-detected from --frontend)
  --server-name NAME      Frontend server_name block to target (default: --frontend)
  --backend-scheme SCHEME Backend URL scheme (default: https)
  --socket-target URL     Socket.IO upstream base (default: http://127.0.0.1:9000)
  --ssh-user USER         Remote SSH login user (default: root)
  --ssh-key PATH          SSH private key path (default: personal)
  --ssh-port PORT         SSH port (default: 22)
  --config-file PATH      Operate on a local config file instead of SSH

Modes:
  --dry-run               Print the resulting diff; do not modify the server
  --check                 Report whether a managed block is present
  --remove                Remove the managed block
  --test                  Run nginx -t remotely
  --reload                Reload nginx remotely
  -h, --help              Show this help

Examples:
  $0 --frontend masaradmin.conceptiqs.com --backend masarbackend.conceptiqs.com
  $0 --frontend admin.example.com --backend frappe.example.com --ssh-user ubuntu
  $0 --config-file /tmp/admin.conf --backend frappe.example.com --dry-run
EOF
}

fail() {
  print_error "$1"
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

resolve_path() {
  local path_value="$1"

  path_value="${path_value/#\~/$HOME}"

  if [[ "$path_value" = /* ]]; then
    echo "$path_value"
    return
  fi

  if [ -e "$PWD/$path_value" ]; then
    printf '%s/%s\n' "$(cd "$(dirname "$PWD/$path_value")" && pwd)" "$(basename "$path_value")"
    return
  fi

  if [ -e "$SCRIPT_DIR/$path_value" ]; then
    printf '%s/%s\n' "$(cd "$(dirname "$SCRIPT_DIR/$path_value")" && pwd)" "$(basename "$path_value")"
    return
  fi

  echo "$path_value"
}

require_helper() {
  require_command python3
  [ -f "$HELPER" ] || fail "Helper script not found: $HELPER"
}

ssh_target() {
  printf '%s@%s' "$SSH_USER" "$FRONTEND_DOMAIN"
}

remote_privileged() {
  local command="$1"
  ssh -i "$SSH_KEY" -p "$SSH_PORT" "$(ssh_target)" \
    "if [ \"\$(id -u)\" -eq 0 ]; then bash -lc $(printf '%q' "$command"); elif sudo -n true >/dev/null 2>&1; then sudo -n bash -lc $(printf '%q' "$command"); else echo 'Passwordless sudo is required for nginx changes. Connect as root or grant this user NOPASSWD sudo access.' >&2; exit 1; fi"
}

detect_config() {
  local matches count
  matches="$(remote_privileged "for f in /etc/nginx/sites-enabled/*; do if grep -qF '$FRONTEND_DOMAIN' \"\$f\" && grep -qE '^[[:space:]]*server_name' \"\$f\"; then readlink -f \"\$f\" | xargs -r basename; fi; done" | sed '/^$/d' || true)"
  count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -eq 1 ]; then
    CONFIG_NAME="$matches"
    print_status "Detected nginx site: $CONFIG_NAME"
  else
    fail "Could not uniquely detect the nginx site for $FRONTEND_DOMAIN (found $count). Pass --config NAME."
  fi
}

CHECK_ONLY=0
DRY_RUN=0
REMOVE=0
TEST_ONLY=0
RELOAD_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontend) FRONTEND_DOMAIN="${2:-}"; shift 2 ;;
    --backend) BACKEND_DOMAIN="${2:-}"; shift 2 ;;
    --config) CONFIG_NAME="${2:-}"; shift 2 ;;
    --server-name) SERVER_NAME="${2:-}"; shift 2 ;;
    --backend-scheme) BACKEND_SCHEME="${2:-}"; shift 2 ;;
    --socket-target) SOCKET_TARGET="${2:-}"; shift 2 ;;
    --ssh-user) SSH_USER="${2:-}"; shift 2 ;;
    --ssh-key) SSH_KEY="${2:-}"; shift 2 ;;
    --ssh-port) SSH_PORT="${2:-}"; shift 2 ;;
    --config-file) CONFIG_FILE="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --check) CHECK_ONLY=1; shift ;;
    --remove) REMOVE=1; shift ;;
    --test) TEST_ONLY=1; shift ;;
    --reload) RELOAD_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown option: $1" ;;
  esac
done

require_helper

LOCAL_MODE=0
if [[ -n "$CONFIG_FILE" ]]; then
  LOCAL_MODE=1
  [ -f "$CONFIG_FILE" ] || fail "Config file not found: $CONFIG_FILE"
else
  [ -n "$FRONTEND_DOMAIN" ] || fail "--frontend is required"
  SSH_KEY="$(resolve_path "$SSH_KEY")"
  [ -f "$SSH_KEY" ] || fail "SSH key not found: $SSH_KEY"
  require_command ssh
  require_command scp
fi

[[ -n "$SERVER_NAME" ]] || SERVER_NAME="$FRONTEND_DOMAIN"

if [[ "$TEST_ONLY" -eq 1 ]]; then
  [[ "$LOCAL_MODE" -eq 0 ]] || fail "--test requires a remote server"
  print_status "Testing nginx configuration on $FRONTEND_DOMAIN..."
  remote_privileged "nginx -t"
  print_success "Nginx configuration test passed"
  exit 0
fi

if [[ "$RELOAD_ONLY" -eq 1 ]]; then
  [[ "$LOCAL_MODE" -eq 0 ]] || fail "--reload requires a remote server"
  print_status "Reloading nginx on $FRONTEND_DOMAIN..."
  remote_privileged "systemctl reload nginx"
  print_success "Nginx reloaded"
  exit 0
fi

NGINX_CONFIG_FILE=""
if [[ "$LOCAL_MODE" -eq 0 ]]; then
  [[ -n "$CONFIG_NAME" ]] || detect_config
  NGINX_CONFIG_FILE="/etc/nginx/sites-available/$CONFIG_NAME"
  [ -n "$CONFIG_NAME" ] || fail "nginx site name could not be resolved; pass --config NAME"
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  if [[ "$LOCAL_MODE" -eq 1 ]]; then
    print_status "Managed Socket.IO block in $CONFIG_FILE: $(python3 "$HELPER" check < "$CONFIG_FILE")"
  else
    print_status "Managed Socket.IO block in $NGINX_CONFIG_FILE: $(remote_privileged "grep -qF '$BEGIN_MARKER' '$NGINX_CONFIG_FILE' && echo present || echo absent")"
  fi
  exit 0
fi

if [[ "$REMOVE" -eq 0 ]]; then
  [ -n "$BACKEND_DOMAIN" ] || fail "--backend is required to apply the proxy"
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
old_conf="$tmp_dir/old.conf"
new_conf="$tmp_dir/new.conf"

if [[ "$LOCAL_MODE" -eq 1 ]]; then
  print_status "Reading local config: $CONFIG_FILE"
  cp "$CONFIG_FILE" "$old_conf"
else
  print_status "Reading remote config: $NGINX_CONFIG_FILE on $FRONTEND_DOMAIN"
  remote_privileged "cat '$NGINX_CONFIG_FILE'" > "$old_conf"
fi

if [[ "$REMOVE" -eq 1 ]]; then
  python3 "$HELPER" remove < "$old_conf" > "$new_conf"
else
  python3 "$HELPER" apply --server-name "$SERVER_NAME" --backend-host "$BACKEND_DOMAIN" \
    --backend-scheme "$BACKEND_SCHEME" --socket-target "$SOCKET_TARGET" < "$old_conf" > "$new_conf"
fi

if cmp -s "$old_conf" "$new_conf"; then
  print_warning "No changes needed."
  exit 0
fi

print_status "Resulting change:"
diff -u "$old_conf" "$new_conf" || true

if [[ "$DRY_RUN" -eq 1 ]]; then
  print_success "Dry run complete; no changes written."
  exit 0
fi

if [[ "$LOCAL_MODE" -eq 1 ]]; then
  print_warning "--config-file mode does not write; rerun with --dry-run to suppress the diff."
  exit 0
fi

remote_tmp="/tmp/add_socketio_proxy.$$.$CONFIG_NAME.conf"
stamp="$(date +%Y%m%d%H%M%S)"

print_status "Uploading updated configuration..."
scp -i "$SSH_KEY" -P "$SSH_PORT" "$new_conf" "$(ssh_target):$remote_tmp"

print_status "Installing, testing, and reloading nginx..."
remote_privileged "cp -a '$NGINX_CONFIG_FILE' '$NGINX_CONFIG_FILE.$stamp.bak' && install -o root -g root -m 644 '$remote_tmp' '$NGINX_CONFIG_FILE' && rm -f '$remote_tmp' && if nginx -t; then systemctl reload nginx; else echo 'nginx -t failed; restoring previous configuration' >&2; cp -a '$NGINX_CONFIG_FILE.$stamp.bak' '$NGINX_CONFIG_FILE'; exit 1; fi"

print_success "Socket.IO proxy applied to $NGINX_CONFIG_FILE on $FRONTEND_DOMAIN"
print_status "Backup: $NGINX_CONFIG_FILE.$stamp.bak"
