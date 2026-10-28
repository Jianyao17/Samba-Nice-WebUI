#!/usr/bin/env bash
set -Eeuo pipefail

# Test/dev entrypoint: run pytest by default, or start smbd and then the WebUI.
if [[ "${PYTEST_ONLY:-1}" == "1" ]]; then
    exec "$@"
fi

# Seed an empty /etc volume from the image defaults. Docker's /etc/hosts,
# /etc/hostname, and /etc/resolv.conf bind mounts must not be overwritten.
if [[ ! -f /etc/passwd && -d /opt/etc-default ]]; then
    find /opt/etc-default -mindepth 1 -maxdepth 1 \
        ! -name hosts ! -name hostname ! -name resolv.conf \
        -exec cp -a {} /etc/ \;
fi

SAMBA_CONF="${SAMBA_CONF:-/etc/samba/smb.conf}"
INCLUDE_CONF="${SAMBA_INCLUDE_CONF_PATH:-/etc/samba/smb.webui.conf}"

mkdir -p /etc/samba /var/run/samba /storage /media
touch "$INCLUDE_CONF"

if [[ ! -f "$SAMBA_CONF" ]]; then
    cat > "$SAMBA_CONF" <<EOF
[global]
   workgroup = WORKGROUP
   server role = standalone server
   security = user
   map to guest = Bad User
   pid directory = /var/run/samba
   include = ${INCLUDE_CONF}
EOF
elif ! grep -qE "^[[:space:]]*include[[:space:]]*=[[:space:]]*${INCLUDE_CONF}[[:space:]]*$" "$SAMBA_CONF"; then
    # Insert the include as the last line of [global] so following shares
    # are not swallowed by the first included section.
    tmp_file="${SAMBA_CONF}.tmp.$$"
    awk -v directive="   include = ${INCLUDE_CONF}" '
        BEGIN { in_global = 0; inserted = 0 }
        /^[ \t]*\[.*\]/ {
            if (in_global && !inserted) {
                print directive
                inserted = 1
            }
            in_global = (tolower($0) ~ /^[ \t]*\[global\][ \t]*$/)
            print
            next
        }
        { print }
        END {
            if (in_global && !inserted) {
                print directive
            }
        }
    ' "$SAMBA_CONF" > "$tmp_file"
    mv "$tmp_file" "$SAMBA_CONF"
fi

# Start the Samba daemon in the same container so user management and shares
# are evaluated against a single identity database.
smbd -D

exec "$@"
