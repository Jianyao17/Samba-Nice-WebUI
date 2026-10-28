#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# If run directly inside the clean container (indicated by internal flag --in-container)
if [[ "${1:-}" == "--in-container" ]]; then
    ARCHIVE_PATH="$2"
    export DEBIAN_FRONTEND=noninteractive

    echo "Checking that container has no Python on PATH..."
    if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
        echo "Error: clean container has Python on PATH!" >&2
        exit 1
    fi

    echo "Installing minimal runtime dependencies (samba-common-bin for testparm, curl)..."
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends samba-common-bin curl

    # Ensure system Python binaries are removed so PATH has no Python outside the bundle
    rm -f /usr/bin/python* /usr/local/bin/python*

    echo "Verifying container has no Python on PATH outside bundle..."
    if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
        echo "Error: Python was found on container PATH outside bundle!" >&2
        exit 1
    fi

    echo "Extracting release bundle to /opt..."
    mkdir -p /opt
    tar --warning=no-timestamp -xzmf "$ARCHIVE_PATH" -C /opt

    if [[ ! -x /opt/samba-nice-webui/venv/bin/samba-nice-webui ]]; then
        echo "Error: bundle entrypoint /opt/samba-nice-webui/venv/bin/samba-nice-webui not executable" >&2
        exit 1
    fi

    TIMESTAMP_FILE="/tmp/smoke_test_timestamp"
    sleep 1
    touch "$TIMESTAMP_FILE"
    sleep 1

    TMP_DIR="$(mktemp -d)"
    TMP_INCLUDE="$TMP_DIR/smb.webui.conf"
    TMP_BACKUP="$TMP_DIR/backups"
    TMP_STORAGE="$TMP_DIR/storage"
    touch "$TMP_INCLUDE"
    mkdir -p "$TMP_BACKUP" "$TMP_STORAGE"

    export SAMBA_INCLUDE_CONF_PATH="$TMP_INCLUDE"
    export SAMBA_BACKUP_DIR="$TMP_BACKUP"
    export ALLOWED_STORAGE_ROOTS="$TMP_STORAGE"
    export WEBUI_HOST="127.0.0.1"
    export WEBUI_PORT="8080"
    export WEBUI_SECRET_KEY="smoke-test-secret-key-at-least-32-chars-long"
    export WEBUI_AUTO_RELOAD="false"
    export PYTHONDONTWRITEBYTECODE="1"
    export PYTHONUNBUFFERED="1"

    echo "Starting WebUI via bundle entrypoint..."
    /opt/samba-nice-webui/venv/bin/samba-nice-webui &
    SERVER_PID=$!

    cleanup() {
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        rm -rf "$TMP_DIR"
    }
    trap cleanup EXIT

    echo "Waiting for WebUI to start on port 8080..."
    SERVER_READY=0
    for _ in {1..30}; do
        if curl -s -f -o /dev/null "http://127.0.0.1:8080/login"; then
            SERVER_READY=1
            break
        fi
        sleep 1
    done

    if [[ "$SERVER_READY" -ne 1 ]]; then
        echo "Error: WebUI did not respond on http://127.0.0.1:8080/login within 30 seconds" >&2
        exit 1
    fi

    STATUS_CODE="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8080/login")"
    if [[ "$STATUS_CODE" != "200" ]]; then
        echo "Error: expected HTTP 200 from /login, got $STATUS_CODE" >&2
        exit 1
    fi
    echo "GET /login returned HTTP 200 OK!"

    # Stop the server and remove the temporary directory once, then disarm the trap
    cleanup
    trap - EXIT

    echo "Checking for newly created __pycache__ files..."
    NEW_CACHES="$(find /opt/samba-nice-webui -name "__pycache__" -newer "$TIMESTAMP_FILE" 2>/dev/null || true)"
    if [[ -n "$NEW_CACHES" ]]; then
        echo "Error: new __pycache__ files detected in bundle directory:" >&2
        echo "$NEW_CACHES" >&2
        exit 1
    fi

    echo "Smoke test passed successfully!"
    exit 0
fi

# Host-side entrypoint: launch clean container
ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" ]]; then
    if [[ -d "$REPO_ROOT/dist" ]]; then
        ARCHIVE="$(find "$REPO_ROOT/dist" -maxdepth 1 -name 'samba-nice-webui-*-linux-x86_64.tar.gz' 2>/dev/null | sort -r | head -n1 || true)"
    fi
fi

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
    echo "Error: release archive not found: $ARCHIVE" >&2
    exit 1
fi

ARCHIVE_ABS="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
echo "Running smoke test for bundle: $ARCHIVE_ABS"

docker run --rm \
    -v "$REPO_ROOT:/repo:ro" \
    -v "$ARCHIVE_ABS:/tmp/bundle.tar.gz:ro" \
    ubuntu:22.04 \
    bash /repo/scripts/tests/test-bundle.sh --in-container /tmp/bundle.tar.gz
