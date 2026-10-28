#!/usr/bin/env bash
set -Eeuo pipefail

# Default configuration and paths
INSTALL_VERSION=""
ADMIN_USER=""
ADMIN_PASSWORD=""
ALLOWED_ROOTS=""
NON_INTERACTIVE=0
NO_SAMBA_CONFIG=0
UNINSTALL=0
PURGE=0
DRY_RUN=0

BASE_URL="${SAMBA_NICE_BASE_URL:-https://github.com/Jianyao17/Samba-Nice-WebUI/releases}"
API_URL="${SAMBA_NICE_API_URL:-https://api.github.com/repos/Jianyao17/Samba-Nice-WebUI/releases}"

INSTALL_DIR="${INSTALL_DIR:-/opt/samba-nice-webui}"
ENV_DIR="${ENV_DIR:-/etc/samba-nice-webui}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/webui.env}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_NAME="samba-nice-webui.service"
DROPIN_DIR="${SYSTEMD_DIR}/${SERVICE_NAME}.d"
DROPIN_FILE="${DROPIN_DIR}/10-storage-roots.conf"
SAMBA_DIR="${SAMBA_DIR:-/etc/samba}"
SMB_CONF="${SAMBA_DIR}/smb.conf"
SMB_WEBUI_CONF="${SAMBA_DIR}/smb.webui.conf"
BACKUP_DIR="${SAMBA_DIR}/.backups"
PID_FILE="${SAMBA_PID_FILE:-/run/samba/smbd.pid}"
SERVICE_PORT="8080"

TMP_DIR=""
SHOW_INSTALL_CREDENTIALS=0
cleanup() {
    if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR:-}" ]]; then
        rm -rf "$TMP_DIR"
    fi
}
trap cleanup EXIT

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

usage() {
    cat <<'EOF'
Samba-Nice-WebUI Bare-Metal Installer

Usage: setup.sh [OPTIONS]

Options:
  --version <tag>         Install a specific release version (default: latest release)
  --admin-user <name>     Admin login username (default: admin)
  --admin-password <pass> Admin login password (default: prompt or generated)
  --allowed-roots <paths> Comma-separated allowed storage roots (default: /mnt)
  --non-interactive       Run without interactive prompts, using defaults or flags
  --no-samba-config       Do not modify /etc/samba/smb.conf
  --uninstall             Stop, disable, and remove the service and application files
  --purge                 With --uninstall, remove managed configuration and backups
  --dry-run               Print planned actions without modifying the system
  -h, --help              Show this help message and exit
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version)
                [[ $# -lt 2 ]] && { echo "Error: --version requires an argument" >&2; exit 1; }
                INSTALL_VERSION="$2"
                shift 2
                ;;
            --admin-user)
                [[ $# -lt 2 ]] && { echo "Error: --admin-user requires an argument" >&2; exit 1; }
                ADMIN_USER="$2"
                shift 2
                ;;
            --admin-password)
                [[ $# -lt 2 ]] && { echo "Error: --admin-password requires an argument" >&2; exit 1; }
                ADMIN_PASSWORD="$2"
                shift 2
                ;;
            --allowed-roots)
                [[ $# -lt 2 ]] && { echo "Error: --allowed-roots requires an argument" >&2; exit 1; }
                ALLOWED_ROOTS="$2"
                shift 2
                ;;
            --non-interactive)
                NON_INTERACTIVE=1
                shift
                ;;
            --no-samba-config)
                NO_SAMBA_CONFIG=1
                shift
                ;;
            --uninstall)
                UNINSTALL=1
                shift
                ;;
            --purge)
                PURGE=1
                shift
                ;;
            --dry-run)
                DRY_RUN=1
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Error: Unknown argument: $1" >&2
                usage >&2
                exit 1
                ;;
        esac
    done
}

preflight_check() {
    # 1. Root check
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "Error: This installer requires root privileges. Please run with sudo." >&2
        exit 1
    fi

    # 2. OS check
    if [[ "$(uname -s)" != "Linux" ]]; then
        echo "Error: This installer requires Linux." >&2
        exit 1
    fi

    # 3. Architecture check
    local arch
    arch="$(uname -m)"
    if [[ "$arch" != "x86_64" ]]; then
        echo "Error: This installer requires x86_64 architecture (got $arch)." >&2
        exit 1
    fi

    # 4. Systemd check
    if ! command -v systemctl >/dev/null 2>&1; then
        echo "Error: This installer requires systemd." >&2
        exit 1
    fi

    # 5. apt check
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "Error: This installer requires apt package manager." >&2
        exit 1
    fi

    # 6. Supported distribution check
    if [[ ! -f /etc/os-release ]]; then
        echo "Error: Cannot identify OS distribution (/etc/os-release missing)." >&2
        exit 1
    fi

    local os_id="" os_ver=""
    # shellcheck disable=SC1091
    os_id="$(. /etc/os-release && echo "$ID")"
    # shellcheck disable=SC1091
    os_ver="$(. /etc/os-release && echo "${VERSION_ID:-}")"

    local supported=0
    case "$os_id" in
        ubuntu)
            if [[ "$os_ver" == "22.04" || "$os_ver" == "24.04" ]]; then
                supported=1
            fi
            ;;
        debian)
            if [[ "$os_ver" == "12" || "$os_ver" == "13" ]]; then
                supported=1
            fi
            ;;
    esac

    if [[ "$supported" -ne 1 ]]; then
        echo "Error: Unsupported distribution or version: $os_id $os_ver. Supported distributions: Debian 12, Debian 13, Ubuntu 22.04, Ubuntu 24.04." >&2
        exit 1
    fi
}

provision_dependencies() {
    echo "Checking and provisioning host dependencies..."
    export DEBIAN_FRONTEND=noninteractive
    local missing_pkgs=()

    for cmd in smbd testparm smbpasswd pdbedit useradd groupadd curl tar openssl; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            case "$cmd" in
                smbd) missing_pkgs+=(samba) ;;
                testparm|smbpasswd|pdbedit) missing_pkgs+=(samba-common-bin) ;;
                useradd|groupadd) missing_pkgs+=(passwd) ;;
                curl) missing_pkgs+=(curl ca-certificates) ;;
                tar) missing_pkgs+=(tar) ;;
                openssl) missing_pkgs+=(openssl) ;;
            esac
        fi
    done

    if [[ ${#missing_pkgs[@]} -gt 0 ]]; then
        echo "Installing missing packages: ${missing_pkgs[*]}..."
        run apt-get update -qq
        run apt-get install -y -qq --no-install-recommends "${missing_pkgs[@]}"
    fi
}

resolve_and_download() {
    TMP_DIR="$(mktemp -d)"

    if [[ -z "$INSTALL_VERSION" ]]; then
        echo "Resolving latest release tag from GitHub..."
        local api_response=""
        # Do not use -f so GitHub's error body (e.g. rate limit) is preserved.
        api_response="$(curl -sSL "$API_URL/latest" 2>/dev/null || true)"
        INSTALL_VERSION="$(echo "$api_response" | grep -m1 '"tag_name":' | cut -d '"' -f4 || true)"
        if [[ -z "$INSTALL_VERSION" ]]; then
            echo "Error: Failed to resolve latest release from GitHub API. Specify --version <tag> directly." >&2
            if [[ -n "$api_response" ]]; then
                echo "$api_response" >&2
            fi
            exit 1
        fi
    fi

    # Strip leading 'v' if present for bundle archive naming
    local clean_version="${INSTALL_VERSION#v}"
    local bundle_name="samba-nice-webui-${clean_version}-linux-x86_64.tar.gz"
    local bundle_url="${BASE_URL}/download/${INSTALL_VERSION}/${bundle_name}"
    local sums_url="${BASE_URL}/download/${INSTALL_VERSION}/SHA256SUMS"

    echo "Downloading release bundle ${INSTALL_VERSION}..."
    # Drop -s so curl can render a progress bar; keep -fL for fail/redirects.
    if ! curl -fL --progress-bar -o "${TMP_DIR}/${bundle_name}" "$bundle_url"; then
        echo "Error: Failed to download release bundle from $bundle_url" >&2
        exit 1
    fi

    echo "Downloading checksums..."
    if ! curl -fsSL -o "${TMP_DIR}/SHA256SUMS" "$sums_url"; then
        echo "Error: Failed to download checksum file from $sums_url" >&2
        exit 1
    fi

    echo "Verifying archive checksum..."
    local expected_sum
    expected_sum="$(grep "$bundle_name" "${TMP_DIR}/SHA256SUMS" | awk '{print $1}')"
    if [[ -z "$expected_sum" ]]; then
        echo "Error: ${bundle_name} not found in SHA256SUMS" >&2
        exit 1
    fi

    local actual_sum
    actual_sum="$(sha256sum "${TMP_DIR}/${bundle_name}" | awk '{print $1}')"
    if [[ "$actual_sum" != "$expected_sum" ]]; then
        echo "Error: Checksum mismatch for ${bundle_name}!" >&2
        echo "Expected: $expected_sum" >&2
        echo "Actual:   $actual_sum" >&2
        exit 1
    fi
    echo "Checksum verified: $actual_sum"
    DOWNLOADED_ARCHIVE="${TMP_DIR}/${bundle_name}"
}

read_env_file_value() {
    # Read KEY=value from an env file; prints the value or nothing.
    local key="$1"
    local file="${2:-$ENV_FILE}"
    local line=""

    [[ -f "$file" ]] || return 0
    line="$(grep -E "^${key}=" "$file" 2>/dev/null | head -n1 || true)"
    [[ -n "$line" ]] || return 0
    printf '%s' "${line#*=}"
}

update_env_file_key() {
    # Replace or append KEY=value in an env file without interpreting the value.
    local key="$1"
    local value="$2"
    local file="$3"
    local tmp

    tmp="$(mktemp)"
    awk -v key="$key" -v val="$value" '
        BEGIN { found = 0 }
        index($0, key "=") == 1 {
            print key "=" val
            found = 1
            next
        }
        { print }
        END {
            if (!found) print key "=" val
        }
    ' "$file" > "$tmp"
    mv "$tmp" "$file"
    chmod 0600 "$file"
}

prompt_credentials_and_roots() {
    if [[ "$DRY_RUN" -eq 1 || "$UNINSTALL" -eq 1 ]]; then
        return 0
    fi

    # Prefer existing webui.env values as defaults (reinstall after uninstall keeps this file).
    local existing_user=""
    local existing_password=""
    local existing_roots=""
    if [[ -f "$ENV_FILE" ]]; then
        existing_user="$(read_env_file_value WEBUI_ADMIN_USER)"
        existing_password="$(read_env_file_value WEBUI_ADMIN_PASSWORD)"
        existing_roots="$(read_env_file_value ALLOWED_STORAGE_ROOTS)"
    fi

    local default_user="${existing_user:-admin}"
    local default_roots="${existing_roots:-/mnt}"

    # Prompt on first install or reinstall after uninstall (app dir removed, env may remain).
    # Skip prompts on in-place updates where both env and install dir already exist.
    local should_prompt=0
    if [[ ! -f "$ENV_FILE" || ! -d "$INSTALL_DIR" ]]; then
        should_prompt=1
        SHOW_INSTALL_CREDENTIALS=1
    fi

    # Check if a controlling terminal is available
    local has_tty=0
    if [[ -c /dev/tty && -t 0 ]]; then
        has_tty=1
    elif [[ -c /dev/tty ]]; then
        has_tty=1
    fi

    if [[ "$should_prompt" -eq 0 || "$NON_INTERACTIVE" -eq 1 || "$has_tty" -eq 0 ]]; then
        # Flags win; otherwise reuse env values, then hard-coded defaults.
        ADMIN_USER="${ADMIN_USER:-$default_user}"
        if [[ -z "$ADMIN_PASSWORD" ]]; then
            if [[ -n "${SAMBA_NICE_ADMIN_PASSWORD:-}" ]]; then
                ADMIN_PASSWORD="$SAMBA_NICE_ADMIN_PASSWORD"
            elif [[ -n "$existing_password" ]]; then
                ADMIN_PASSWORD="$existing_password"
            else
                ADMIN_PASSWORD="$(openssl rand -hex 12)"
            fi
        fi
        ALLOWED_ROOTS="${ALLOWED_ROOTS:-$default_roots}"
        return 0
    fi

    # 1. Admin username
    if [[ -z "$ADMIN_USER" ]]; then
        printf "Admin username [%s]: " "$default_user" > /dev/tty
        local user_in=""
        read -r user_in < /dev/tty || user_in=""
        ADMIN_USER="${user_in:-$default_user}"
    fi

    # 2. Admin password
    if [[ -z "$ADMIN_PASSWORD" ]]; then
        if [[ -n "${SAMBA_NICE_ADMIN_PASSWORD:-}" ]]; then
            ADMIN_PASSWORD="$SAMBA_NICE_ADMIN_PASSWORD"
        else
            if [[ -n "$existing_password" ]]; then
                printf "Admin password [leave blank to keep existing]: " > /dev/tty
            else
                printf "Admin password [leave blank to generate]: " > /dev/tty
            fi
            local pass_in=""
            read -rs pass_in < /dev/tty || pass_in=""
            echo "" > /dev/tty
            if [[ -z "$pass_in" ]]; then
                if [[ -n "$existing_password" ]]; then
                    ADMIN_PASSWORD="$existing_password"
                else
                    ADMIN_PASSWORD="$(openssl rand -hex 12)"
                fi
            else
                ADMIN_PASSWORD="$pass_in"
            fi
        fi
    fi

    # 3. Allowed storage roots
    if [[ -z "$ALLOWED_ROOTS" ]]; then
        printf "Allowed storage roots [%s]: " "$default_roots" > /dev/tty
        local roots_in=""
        read -r roots_in < /dev/tty || roots_in=""
        ALLOWED_ROOTS="${roots_in:-$default_roots}"
    fi
}

validate_storage_roots() {
    local raw_roots="${1:-/mnt}"
    local clean_roots=()
    local seen_roots=()

    IFS=',' read -ra ADDR <<< "$raw_roots"
    for r in "${ADDR[@]}"; do
        # Strip leading and trailing whitespace
        local trimmed
        trimmed="$(echo "$r" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        [[ -z "$trimmed" ]] && continue

        # Validation 1: Absolute path
        if [[ "$trimmed" != /* ]]; then
            echo "Error: Storage root must be an absolute path: $trimmed" >&2
            return 1
        fi

        # Validation 2: Overlapping /etc/samba rejection
        if [[ "$trimmed" == "/etc/samba" || "$trimmed" == /etc/samba/* ]]; then
            echo "Error: Storage root cannot overlap Samba configuration directory (/etc/samba): $trimmed" >&2
            return 1
        fi

        # Collapse duplicates while preserving order
        local already_seen=0
        for s in "${seen_roots[@]:-}"; do
            if [[ "$s" == "$trimmed" ]]; then
                already_seen=1
                break
            fi
        done
        if [[ "$already_seen" -eq 0 ]]; then
            seen_roots+=("$trimmed")
            clean_roots+=("$trimmed")
        fi
    done

    if [[ ${#clean_roots[@]} -eq 0 ]]; then
        clean_roots=("/mnt")
    fi

    VALIDATED_ROOTS=("${clean_roots[@]}")
    VALIDATED_ROOTS_CSV="$(IFS=,; echo "${clean_roots[*]}")"
}

setup_storage_roots_dropin() {
    local roots=("$@")
    echo "Configuring storage roots drop-in: ${roots[*]}..."

    for r in "${roots[@]}"; do
        if [[ ! -d "$r" ]]; then
            run mkdir -p "$r"
            run chmod 0755 "$r"
        fi
    done

    run mkdir -p "$DROPIN_DIR"
    local dropin_content
    dropin_content="[Service]
ReadWritePaths=${roots[*]}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry-run] Write to $DROPIN_FILE:"
        echo "$dropin_content"
    else
        echo "$dropin_content" > "$DROPIN_FILE"
    fi
}

setup_env_file() {
    run mkdir -p "$ENV_DIR"

    if [[ -f "$ENV_FILE" ]]; then
        local current_user current_password current_roots
        current_user="$(read_env_file_value WEBUI_ADMIN_USER)"
        current_password="$(read_env_file_value WEBUI_ADMIN_PASSWORD)"
        current_roots="$(read_env_file_value ALLOWED_STORAGE_ROOTS)"

        local update_user=0
        local update_password=0
        local update_roots=0

        if [[ -n "${ADMIN_USER:-}" && "$ADMIN_USER" != "$current_user" ]]; then
            update_user=1
        fi
        if [[ -n "${ADMIN_PASSWORD:-}" && "$ADMIN_PASSWORD" != "$current_password" ]]; then
            update_password=1
        fi
        if [[ -n "${ALLOWED_ROOTS:-}" && "${VALIDATED_ROOTS_CSV:-}" != "$current_roots" ]]; then
            update_roots=1
        fi

        if [[ "$update_user" -eq 0 && "$update_password" -eq 0 && "$update_roots" -eq 0 ]]; then
            return 0
        fi

        echo "Updating existing environment file..."
        local bak_file
        bak_file="${ENV_FILE}.bak.$(date -u +%Y%m%d%H%M%S)"
        run cp -a "$ENV_FILE" "$bak_file"

        if [[ "$DRY_RUN" -eq 1 ]]; then
            [[ "$update_user" -eq 1 ]] && echo "[dry-run] set WEBUI_ADMIN_USER=${ADMIN_USER}"
            [[ "$update_password" -eq 1 ]] && echo "[dry-run] set WEBUI_ADMIN_PASSWORD=<redacted>"
            [[ "$update_roots" -eq 1 ]] && echo "[dry-run] set ALLOWED_STORAGE_ROOTS=${VALIDATED_ROOTS_CSV}"
            return 0
        fi

        [[ "$update_user" -eq 1 ]] && update_env_file_key WEBUI_ADMIN_USER "$ADMIN_USER" "$ENV_FILE"
        [[ "$update_password" -eq 1 ]] && update_env_file_key WEBUI_ADMIN_PASSWORD "$ADMIN_PASSWORD" "$ENV_FILE"
        [[ "$update_roots" -eq 1 ]] && update_env_file_key ALLOWED_STORAGE_ROOTS "$VALIDATED_ROOTS_CSV" "$ENV_FILE"
        return 0
    fi

    echo "Generating new environment file at $ENV_FILE..."
    local secret_key
    secret_key="$(openssl rand -hex 32)"

    local env_content
    env_content="WEBUI_HOST=0.0.0.0
WEBUI_PORT=${SERVICE_PORT}
WEBUI_ADMIN_USER=${ADMIN_USER}
WEBUI_ADMIN_PASSWORD=${ADMIN_PASSWORD}
WEBUI_SECRET_KEY=${secret_key}
WEBUI_AUTO_RELOAD=false
SAMBA_INCLUDE_CONF_PATH=${SMB_WEBUI_CONF}
SAMBA_BACKUP_DIR=${BACKUP_DIR}
SAMBA_PID_FILE=${PID_FILE}
ALLOWED_STORAGE_ROOTS=${VALIDATED_ROOTS_CSV}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry-run] Write mode 0600 $ENV_FILE:"
        echo "$env_content"
    else
        echo "$env_content" > "$ENV_FILE"
        chmod 0600 "$ENV_FILE"
    fi
}

install_bundle() {
    local staging_dir="${INSTALL_DIR}.new"
    local previous_dir="${INSTALL_DIR}.previous"

    echo "Extracting bundle to staging directory..."
    run rm -rf "$staging_dir"
    run mkdir -p "$staging_dir"
    run tar -xzf "$DOWNLOADED_ARCHIVE" --strip-components=1 -C "$staging_dir"

    if [[ "$DRY_RUN" -eq 0 && ! -x "${staging_dir}/venv/bin/samba-nice-webui" ]]; then
        echo "Error: Staged entrypoint not executable: ${staging_dir}/venv/bin/samba-nice-webui" >&2
        exit 1
    fi

    # Ensure required Samba directories exist
    run mkdir -p "$SAMBA_DIR"
    run mkdir -p "$BACKUP_DIR"
    if [[ ! -f "$SMB_WEBUI_CONF" ]]; then
        run touch "$SMB_WEBUI_CONF"
    fi

    # Swap directories
    echo "Applying new installation..."
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo "Stopping running service..."
        run systemctl stop "$SERVICE_NAME"
    fi

    run rm -rf "$previous_dir"
    if [[ -d "$INSTALL_DIR" ]]; then
        run mv "$INSTALL_DIR" "$previous_dir"
    fi
    run mv "$staging_dir" "$INSTALL_DIR"

    # Install systemd service unit
    run cp "${INSTALL_DIR}/samba-nice-webui.service" "${SYSTEMD_DIR}/${SERVICE_NAME}"
    run systemctl daemon-reload
    run systemctl enable "$SERVICE_NAME"
    run systemctl start "$SERVICE_NAME"

    # Poll service health
    if [[ "$DRY_RUN" -eq 0 ]]; then
        echo "Verifying service status..."
        local active=0
        for _ in {1..15}; do
            if systemctl is-active --quiet "$SERVICE_NAME"; then
                active=1
                break
            fi
            sleep 1
        done

        if [[ "$active" -ne 1 ]]; then
            echo "Error: Service failed to start!" >&2
            journalctl -u "$SERVICE_NAME" -n 25 --no-pager >&2 || true

            if [[ -d "$previous_dir" ]]; then
                echo "Rolling back to previous installation..."
                rm -rf "$INSTALL_DIR"
                mv "$previous_dir" "$INSTALL_DIR"
                systemctl restart "$SERVICE_NAME" || true
            fi
            exit 1
        fi
        rm -rf "$previous_dir"
    fi
}

insert_samba_include() {
    local conf_file="$1"
    local include_line="$2"
    local tmp_file="${conf_file}.tmp.$$"

    awk -v directive="$include_line" '
    BEGIN { in_global = 0; inserted = 0; has_global = 0 }
    {
        line = $0
        if (line ~ /^[ \t]*\[.*\]/) {
            if (in_global && !inserted) {
                print directive
                inserted = 1
                in_global = 0
            }
            if (tolower(line) ~ /^[ \t]*\[global\]/) {
                has_global = 1
                in_global = 1
            } else {
                in_global = 0
            }
        }
        print line
    }
    END {
        if (in_global && !inserted) {
            print directive
            inserted = 1
        }
        if (!has_global) {
            exit 2
        }
    }
    ' "$conf_file" > "$tmp_file"

    local awk_status=$?
    if [[ $awk_status -ne 0 ]]; then
        rm -f "$tmp_file"
        return $awk_status
    fi

    cat "$tmp_file" > "$conf_file"
    rm -f "$tmp_file"
    return 0
}

remove_samba_include() {
    local conf_file="$1"
    local include_pattern="$2"
    local tmp_file="${conf_file}.tmp.$$"

    grep -v -E "$include_pattern" "$conf_file" > "$tmp_file" || true
    cat "$tmp_file" > "$conf_file"
    rm -f "$tmp_file"
}

bootstrap_samba_include() {
    if [[ "$NO_SAMBA_CONFIG" -eq 1 ]]; then
        echo "Skipping Samba configuration edit (--no-samba-config)."
        return 0
    fi

    if [[ ! -f "$SMB_CONF" ]]; then
        echo "Warning: $SMB_CONF not found. Skipping include bootstrap." >&2
        return 0
    fi

    local target_include="   include = ${SMB_WEBUI_CONF}"

    # Check if include directive already exists
    if grep -q -E "^[[:space:]]*include[[:space:]]*=[[:space:]]*${SMB_WEBUI_CONF}" "$SMB_CONF"; then
        echo "Include directive already present in $SMB_CONF."
        if command -v testparm >/dev/null 2>&1; then
            testparm -s "$SMB_CONF" >/dev/null 2>&1 || true
        fi
        return 0
    fi

    echo "Backing up and adding include directive to $SMB_CONF..."
    local bak_file
    bak_file="${SMB_CONF}.bak.$(date -u +%Y%m%d%H%M%S)"
    run cp -a "$SMB_CONF" "$bak_file"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry-run] Insert '$target_include' into [global] of $SMB_CONF"
        return 0
    fi

    if ! insert_samba_include "$SMB_CONF" "$target_include"; then
        echo "Warning: [global] section not found in $SMB_CONF. Restoring backup." >&2
        cp -a "$bak_file" "$SMB_CONF"
        return 0
    fi

    # Validate with testparm
    if command -v testparm >/dev/null 2>&1; then
        if ! testparm -s "$SMB_CONF" >/dev/null 2>&1; then
            echo "Error: testparm validation failed for $SMB_CONF! Restoring backup..." >&2
            cp -a "$bak_file" "$SMB_CONF"
            exit 1
        fi
    fi

    # Reload smbd if active
    if systemctl is-active --quiet smbd 2>/dev/null; then
        echo "Reloading smbd service..."
        systemctl reload smbd 2>/dev/null || true
    fi
}

uninstall_service() {
    echo "Uninstalling Samba-Nice-WebUI..."

    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        run systemctl stop "$SERVICE_NAME"
    fi
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        run systemctl disable "$SERVICE_NAME"
    fi

    run rm -f "${SYSTEMD_DIR}/${SERVICE_NAME}"
    run rm -rf "$DROPIN_DIR"
    run systemctl daemon-reload 2>/dev/null || true

    run rm -rf "$INSTALL_DIR"

    if [[ "$PURGE" -eq 1 ]]; then
        echo "Purging configuration and backups..."
        run rm -rf "$ENV_DIR"
        run rm -f "$SMB_WEBUI_CONF"
        run rm -rf "$BACKUP_DIR"

        if [[ -f "$SMB_CONF" ]]; then
            local bak_file
            bak_file="${SMB_CONF}.bak.$(date -u +%Y%m%d%H%M%S)"
            run cp -a "$SMB_CONF" "$bak_file"
            if [[ "$DRY_RUN" -eq 0 ]]; then
                remove_samba_include "$SMB_CONF" "^[[:space:]]*include[[:space:]]*=[[:space:]]*${SMB_WEBUI_CONF}"
                if command -v testparm >/dev/null 2>&1; then
                    testparm -s "$SMB_CONF" >/dev/null 2>&1 || cp -a "$bak_file" "$SMB_CONF"
                fi
            fi
        fi
    fi

    echo "Uninstallation complete."
    exit 0
}

main() {
    parse_args "$@"

    if [[ "$UNINSTALL" -eq 1 ]]; then
        uninstall_service
    fi

    preflight_check
    provision_dependencies
    prompt_credentials_and_roots
    validate_storage_roots "${ALLOWED_ROOTS:-/mnt}"
    resolve_and_download
    setup_env_file
    setup_storage_roots_dropin "${VALIDATED_ROOTS[@]}"
    install_bundle
    bootstrap_samba_include

    echo ""
    echo "====================================================="
    echo "Samba-Nice-WebUI installed successfully!"
    echo "====================================================="
    echo "Access URL:      http://<server-ip>:${SERVICE_PORT} (or http://localhost:${SERVICE_PORT})"
    if [[ "$SHOW_INSTALL_CREDENTIALS" -eq 1 ]]; then
        echo "Admin Username:  ${ADMIN_USER}"
        echo "Admin Password:  ${ADMIN_PASSWORD}"
    else
        echo "Admin credentials: unchanged (see ${ENV_FILE})"
    fi
    echo "Storage Roots:   ${VALIDATED_ROOTS_CSV}"
    echo "====================================================="
}

# Run main when executed as a file or piped to bash; skip when sourced.
# Under `set -u`, bare BASH_SOURCE[0] fails when the script is fed via stdin
# (curl | bash) because the array entry is unset.
if [[ -z "${BASH_SOURCE[0]:-}" || "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
