#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Run the build inside the pinned Ubuntu container unless already inside it
if [[ "${1:-}" != "--in-container" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "Error: docker is required to build the release bundle." >&2
        exit 1
    fi

    echo "Starting bundle build in ubuntu:22.04..."
    docker run --rm \
        -e "VERSION=${VERSION:-}" \
        -e "OUTPUT_DIR=${OUTPUT_DIR:-}" \
        -e "HOST_UID=$(id -u)" \
        -e "HOST_GID=$(id -g)" \
        -v "$REPO_ROOT:/repo" \
        -w /repo \
        ubuntu:22.04 \
        bash /repo/scripts/build-bundle.sh --in-container
    exit 0
fi

# Pinned versions
PYTHON_VERSION="3.12.7"
PYTHON_RELEASE_TAG="20241016"
PYTHON_ARCHIVE="cpython-${PYTHON_VERSION}+${PYTHON_RELEASE_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_RELEASE_TAG}/${PYTHON_ARCHIVE}"

UV_VERSION="0.5.26"
UV_ARCHIVE="uv-x86_64-unknown-linux-gnu.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_ARCHIVE}"

VERSION="${VERSION:-}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/dist}"
TARGET_DIR="/opt/samba-nice-webui"

# Ensure required system utilities
export DEBIAN_FRONTEND=noninteractive
if ! command -v curl >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
    echo "Installing required utilities (curl, tar, git, ca-certificates)..."
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends curl tar git ca-certificates
fi

# Resolve the release version from an explicit override, then the exact git tag, then pyproject.toml
if [[ -z "$VERSION" ]]; then
    GIT_TAG="$(git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || true)"
    if [[ -n "$GIT_TAG" ]]; then
        VERSION="${GIT_TAG#v}"
    else
        VERSION="$(grep -m1 '^version = ' "$REPO_ROOT/pyproject.toml" | cut -d '"' -f2)"
    fi
fi
VERSION="${VERSION#v}"
BUNDLE_NAME="samba-nice-webui-${VERSION}-linux-x86_64.tar.gz"
BUNDLE_PATH="$OUTPUT_DIR/$BUNDLE_NAME"

sync_project_version() {
    local pyproject="$REPO_ROOT/pyproject.toml"
    local lockfile="$REPO_ROOT/uv.lock"
    local current
    current="$(grep -m1 '^version = ' "$pyproject" | cut -d '"' -f2)"

    if [[ "$current" == "$VERSION" ]]; then
        return 0
    fi

    echo "Syncing project version ${current} -> ${VERSION}..."
    sed -i -E "0,/^version = \"[^\"]*\"$/s//version = \"${VERSION}\"/" "$pyproject"

    if [[ -f "$lockfile" ]]; then
        sed -i -E "/^name = \"samba-nice-webui\"$/{n;s/^version = \"[^\"]*\"$/version = \"${VERSION}\"/;}" "$lockfile"
    fi
}

echo "Building Samba-Nice-WebUI bundle v${VERSION}..."

# Keep pyproject.toml and uv.lock aligned with the release tag
sync_project_version

# Ensure uv is available
if ! command -v uv >/dev/null 2>&1; then
    echo "Downloading uv ${UV_VERSION}..."
    TMP_UV_DIR="$(mktemp -d)"
    curl -fsSL --retry 3 --retry-delay 2 "$UV_URL" | tar -xz -C "$TMP_UV_DIR"
    find "$TMP_UV_DIR" -name uv -type f -exec cp {} /usr/local/bin/uv \;
    find "$TMP_UV_DIR" -name uvx -type f -exec cp {} /usr/local/bin/uvx \;
    chmod +x /usr/local/bin/uv /usr/local/bin/uvx
    rm -rf "$TMP_UV_DIR"
fi

# Prepare target directory
echo "Setting up ${TARGET_DIR}..."
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

# Download and extract standalone Python runtime
echo "Downloading standalone Python ${PYTHON_VERSION} (${PYTHON_RELEASE_TAG})..."
curl -fsSL --retry 3 --retry-delay 2 "$PYTHON_URL" | tar -xz -C "$TARGET_DIR"

if [[ ! -x "$TARGET_DIR/python/bin/python3" ]]; then
    echo "Error: Python runtime not found at $TARGET_DIR/python/bin/python3" >&2
    exit 1
fi

# Create virtualenv using standalone Python runtime
echo "Creating virtualenv at ${TARGET_DIR}/venv..."
uv venv "$TARGET_DIR/venv" --python "$TARGET_DIR/python/bin/python3"

# Install application and locked dependencies into target virtualenv
echo "Installing application and dependencies with uv..."
(
    cd "$REPO_ROOT"
    sync_ok=0
    for attempt in 1 2 3; do
        if UV_PROJECT_ENVIRONMENT="$TARGET_DIR/venv" \
           UV_COMPILE_BYTECODE=1 \
           UV_HTTP_RETRIES=8 \
           UV_HTTP_TIMEOUT=60 \
           UV_CONCURRENT_DOWNLOADS=4 \
           uv sync \
               --locked \
               --no-dev \
               --no-editable \
               --python "$TARGET_DIR/python/bin/python3"; then
            sync_ok=1
            break
        fi
        echo "uv sync failed on attempt ${attempt}/3. Retrying in 5 seconds..."
        sleep 5
    done
    if [[ "$sync_ok" -ne 1 ]]; then
        echo "Error: uv sync failed after 3 attempts." >&2
        exit 1
    fi
)

# Copy metadata and service unit into bundle layout
echo "$VERSION" > "$TARGET_DIR/VERSION"
cp "$REPO_ROOT/LICENSE" "$TARGET_DIR/LICENSE"
cp "$REPO_ROOT/packaging/samba-nice-webui.service" "$TARGET_DIR/samba-nice-webui.service"

# Verify console script exists and shebang references target path
if [[ ! -x "$TARGET_DIR/venv/bin/samba-nice-webui" ]]; then
    echo "Error: console script not installed at $TARGET_DIR/venv/bin/samba-nice-webui" >&2
    exit 1
fi

echo "Verifying bundle entrypoint..."
# Verify shebang references the target virtualenv interpreter
ENTRYPOINT_SHEBANG="$(head -n 1 "$TARGET_DIR/venv/bin/samba-nice-webui")"
if [[ "$ENTRYPOINT_SHEBANG" != "#!$TARGET_DIR/venv/bin/python"* ]]; then
    echo "Error: unexpected shebang in entrypoint: $ENTRYPOINT_SHEBANG" >&2
    exit 1
fi

# Verify the bundled standalone Python interpreter runs and can import the application
"$TARGET_DIR/venv/bin/python" --version
"$TARGET_DIR/venv/bin/python" -c "import src; print('Bundle entrypoint and application packages verified successfully.')"

# Package into tarball
mkdir -p "$OUTPUT_DIR"
BUILD_DATE="$(date -u +'%Y-%m-%d %H:%M:%SZ')"
echo "Creating archive at ${BUNDLE_PATH}..."
tar --clamp-mtime --mtime="$BUILD_DATE" -czf "$BUNDLE_PATH" -C /opt samba-nice-webui

echo "Archive layout check:"
tar -tzf "$BUNDLE_PATH" > /tmp/tar_contents.txt
head -n 15 /tmp/tar_contents.txt
rm -f /tmp/tar_contents.txt

# Check archive size (must be under 200 MB)
ARCHIVE_SIZE_BYTES="$(wc -c < "$BUNDLE_PATH")"
ARCHIVE_SIZE_MB=$((ARCHIVE_SIZE_BYTES / 1024 / 1024))
echo "Archive size: ${ARCHIVE_SIZE_MB} MB (${ARCHIVE_SIZE_BYTES} bytes)"

if [[ "$ARCHIVE_SIZE_MB" -ge 200 ]]; then
    echo "Error: archive size exceeds 200 MB limit (${ARCHIVE_SIZE_MB} MB)" >&2
    exit 1
fi

# Hand build outputs back to the invoking user because the container writes as root
if [[ -n "${HOST_UID:-}" && -n "${HOST_GID:-}" ]]; then
    echo "Restoring ownership of build outputs to ${HOST_UID}:${HOST_GID}..."
    chown -R "${HOST_UID}:${HOST_GID}" "$OUTPUT_DIR"
    if [[ -f "$REPO_ROOT/pyproject.toml" ]]; then
        chown "${HOST_UID}:${HOST_GID}" "$REPO_ROOT/pyproject.toml"
    fi
    if [[ -f "$REPO_ROOT/uv.lock" ]]; then
        chown "${HOST_UID}:${HOST_GID}" "$REPO_ROOT/uv.lock"
    fi
fi

echo "Bundle built successfully: ${BUNDLE_PATH}"
