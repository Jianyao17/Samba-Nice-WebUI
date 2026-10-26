from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "setup.sh"


def _bash_candidates() -> list[str]:
    """
    Ordered bash candidates to check on this host.
    """
    candidates: list[str] = []
    if os.name == "nt":
        for path in (
            r"C:\Windows\system32\bash.exe",
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ):
            if Path(path).is_file():
                candidates.append(path)

    which_bash = shutil.which("bash")
    if which_bash:
        candidates.append(which_bash)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _detect_bash() -> tuple[str | None, bool]:
    """
    Find a functional bash executable and detect whether it runs under WSL.
    Verifies that the shell can actually fork processes and subshells.
    """
    for candidate in _bash_candidates():
        try:
            res = subprocess.run(
                [candidate, "-c", "(echo ok)"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode != 0 or res.stdout.strip() != "ok":
                continue

            is_wsl = False
            uname_res = subprocess.run(
                [candidate, "-c", "uname -r"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if uname_res.returncode == 0:
                kernel = uname_res.stdout.lower()
                if "microsoft" in kernel or "wsl" in kernel:
                    is_wsl = True

            return candidate, is_wsl
        except Exception:
            continue

    return None, False


BASH_BIN, IS_WSL = _detect_bash()


def to_bash_path(path: Path | str) -> str:
    """
    Format a path for the detected bash environment.
    """
    path_obj = Path(path).resolve()
    posix = path_obj.as_posix()
    if IS_WSL and len(posix) >= 2 and posix[1] == ":":
        drive = posix[0].lower()
        return f"/mnt/{drive}{posix[2:]}"
    return posix


def to_wsl_path(text: str) -> str:
    """
    Translate Windows drive paths (C:/... or C:\\...) to WSL paths (/mnt/c/...).
    """
    def repl(m: re.Match[str]) -> str:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"

    return re.sub(r"([A-Za-z]):[/\\]([^\s\"'>;&|,]+)", repl, text)


def from_wsl_path(text: str) -> str:
    """
    Translate WSL paths (/mnt/c/...) back to Windows drive paths (C:/...).
    """
    def repl(m: re.Match[str]) -> str:
        drive = m.group(1).upper()
        rest = m.group(2)
        return f"{drive}:/{rest}"

    return re.sub(r"/mnt/([a-zA-Z])/([^\s\"'<;&|,]+)", repl, text)


def run_bash_code(
    script_snippet: str,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Run a bash script snippet, sourcing setup.sh first.
    """
    if not BASH_BIN:
        pytest.skip("Bash is unavailable or non-functional on this host")

    script_target = to_bash_path(INSTALL_SCRIPT)
    full_cmd = f'source "{script_target}"\n{script_snippet}'
    if IS_WSL:
        full_cmd = to_wsl_path(full_cmd)

    full_cmd_clean = full_cmd.replace("\r\n", "\n").replace("\r", "\n")

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    res = subprocess.run(
        [BASH_BIN, "--norc", "--noprofile"],
        input=full_cmd_clean.encode("utf-8"),
        capture_output=True,
        env=proc_env,
        cwd=cwd or REPO_ROOT,
        timeout=30,
    )
    stdout = res.stdout.decode("utf-8", errors="replace")
    stderr = res.stderr.decode("utf-8", errors="replace")
    if IS_WSL:
        stdout = from_wsl_path(stdout)
        stderr = from_wsl_path(stderr)

    return subprocess.CompletedProcess(
        args=res.args,
        returncode=res.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_install_script_can_be_sourced_without_executing_main():
    """
    Sourcing setup.sh must not execute main().
    """
    res = run_bash_code('echo "SOURCE_SUCCESS"')
    assert res.returncode == 0
    assert "SOURCE_SUCCESS" in res.stdout
    assert "Samba-Nice-WebUI installed successfully!" not in res.stdout


def test_argument_parsing_help():
    """
    The --help option must display usage and return 0.
    """
    if not BASH_BIN:
        pytest.skip("Bash is unavailable or non-functional on this host")

    script_target = to_bash_path(INSTALL_SCRIPT)
    res = subprocess.run(
        [BASH_BIN, script_target, "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode == 0
    for flag in [
        "--version",
        "--admin-user",
        "--admin-password",
        "--allowed-roots",
        "--non-interactive",
        "--no-samba-config",
        "--uninstall",
        "--purge",
        "--dry-run",
    ]:
        assert flag in res.stdout


def test_argument_parsing_unknown_option():
    """
    An unknown option must exit non-zero before modifying the system.
    """
    if not BASH_BIN:
        pytest.skip("Bash is unavailable or non-functional on this host")

    script_target = to_bash_path(INSTALL_SCRIPT)
    res = subprocess.run(
        [BASH_BIN, script_target, "--unknown-flag"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode != 0
    assert "Unknown argument: --unknown-flag" in res.stderr
    assert "Unknown argument: --unknown-flag" in res.stderr


def test_storage_roots_validation_and_deduplication():
    """
    Storage roots must be validated, duplicates collapsed, and invalid paths rejected.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()

        # Valid roots with duplicate and whitespace
        code = f"""
        validate_storage_roots "{tmp_path}/data1, {tmp_path}/data2 , {tmp_path}/data1"
        echo "CSV: $VALIDATED_ROOTS_CSV"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        assert f"CSV: {tmp_path}/data1,{tmp_path}/data2" in res.stdout

        # Reject relative path
        code_rel = 'validate_storage_roots "relative/path"'
        res_rel = run_bash_code(code_rel)
        assert res_rel.returncode != 0
        assert "Storage root must be an absolute path" in res_rel.stderr

        # Accept the root filesystem as a storage root
        code_root = """
        validate_storage_roots "/"
        echo "CSV: $VALIDATED_ROOTS_CSV"
        """
        res_root = run_bash_code(code_root)
        assert res_root.returncode == 0
        assert "CSV: /" in res_root.stdout

        # Reject overlapping /etc/samba
        code_samba = 'validate_storage_roots "/etc/samba/data"'
        res_samba = run_bash_code(code_samba)
        assert res_samba.returncode != 0
        assert "cannot overlap Samba configuration directory" in res_samba.stderr


def test_storage_roots_dropin_creation():
    """
    The drop-in must contain ReadWritePaths for all validated roots.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        dropin_dir = f"{tmp_path}/systemd/samba-nice-webui.service.d"
        dropin_file = f"{dropin_dir}/10-storage-roots.conf"
        root1 = f"{tmp_path}/mnt/data1"
        root2 = f"{tmp_path}/mnt/data2"

        code = f"""
        DROPIN_DIR="{dropin_dir}"
        DROPIN_FILE="{dropin_file}"
        setup_storage_roots_dropin "{root1}" "{root2}"
        cat "$DROPIN_FILE"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        assert f"ReadWritePaths={root1} {root2}" in res.stdout
        assert Path(root1).is_dir()
        assert Path(root2).is_dir()


def test_setup_env_file_fresh_and_rerun():
    """
    Fresh install creates 0600 env file; re-run without --allowed-roots preserves it.
    Re-run with --allowed-roots updates only ALLOWED_STORAGE_ROOTS and creates a backup.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        env_dir = f"{tmp_path}/etc/samba-nice-webui"
        env_file = f"{env_dir}/webui.env"
        samba_dir = f"{tmp_path}/etc/samba"

        # 1. Fresh install
        code_fresh = f"""
        ENV_DIR="{env_dir}"
        ENV_FILE="{env_file}"
        SAMBA_DIR="{samba_dir}"
        SMB_WEBUI_CONF="{samba_dir}/smb.webui.conf"
        BACKUP_DIR="{samba_dir}/.backups"
        ADMIN_USER="testadmin"
        ADMIN_PASSWORD="supersecretpassword"
        VALIDATED_ROOTS_CSV="/mnt/primary"
        setup_env_file
        """
        res = run_bash_code(code_fresh)
        assert res.returncode == 0

        env_file_path = Path(env_file)
        assert env_file_path.exists()
        content1 = env_file_path.read_text()
        assert "WEBUI_ADMIN_USER=testadmin" in content1
        assert "WEBUI_ADMIN_PASSWORD=supersecretpassword" in content1
        assert "ALLOWED_STORAGE_ROOTS=/mnt/primary" in content1
        assert "WEBUI_SECRET_KEY=" in content1

        # 2. Re-run without ALLOWED_ROOTS preserves file byte-for-byte
        code_rerun = f"""
        ENV_DIR="{env_dir}"
        ENV_FILE="{env_file}"
        ALLOWED_ROOTS=""
        setup_env_file
        """
        res_rerun = run_bash_code(code_rerun)
        assert res_rerun.returncode == 0
        content2 = env_file_path.read_text()
        assert content1 == content2

        # 3. Re-run with ALLOWED_ROOTS updates only that line and makes backup
        code_update = f"""
        ENV_DIR="{env_dir}"
        ENV_FILE="{env_file}"
        ALLOWED_ROOTS="/mnt/updated"
        VALIDATED_ROOTS_CSV="/mnt/updated"
        setup_env_file
        """
        res_update = run_bash_code(code_update)
        assert res_update.returncode == 0
        content3 = env_file_path.read_text()
        assert "ALLOWED_STORAGE_ROOTS=/mnt/updated" in content3
        assert "WEBUI_ADMIN_PASSWORD=supersecretpassword" in content3

        # Confirm backup was created
        backups = list(Path(env_dir).glob("webui.env.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == content1


def test_samba_include_insertion_before_next_section():
    """
    Include directive must be inserted as last line of [global], before next section.
    """
    initial_conf = """[global]
   workgroup = WORKGROUP
   server string = Samba Server

[share1]
   path = /data
   read only = no
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(initial_conf)
        conf_path = f.name

    try:
        code = f"""
        insert_samba_include "{conf_path}" "   include = /etc/samba/smb.webui.conf"
        cat "{conf_path}"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        lines = res.stdout.strip().splitlines()
        include_idx = -1
        share_idx = -1
        for idx, line in enumerate(lines):
            if "include = /etc/samba/smb.webui.conf" in line:
                include_idx = idx
            if "[share1]" in line:
                share_idx = idx

        assert include_idx != -1
        assert share_idx != -1
        assert include_idx < share_idx
    finally:
        os.unlink(conf_path)


def test_samba_include_insertion_at_end_of_file():
    """
    Include directive must be inserted at end of file if [global] is the only section.
    """
    initial_conf = """[global]
   workgroup = WORKGROUP
   server string = Samba Server
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(initial_conf)
        conf_path = f.name

    try:
        code = f"""
        insert_samba_include "{conf_path}" "   include = /etc/samba/smb.webui.conf"
        cat "{conf_path}"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        assert "include = /etc/samba/smb.webui.conf" in res.stdout
    finally:
        os.unlink(conf_path)


def test_samba_include_missing_global_returns_nonzero():
    """
    If no [global] section exists, insert_samba_include must return non-zero.
    """
    initial_conf = """[share1]
   path = /data
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(initial_conf)
        conf_path = f.name

    try:
        code = f"""
        insert_samba_include "{conf_path}" "   include = /etc/samba/smb.webui.conf"
        """
        res = run_bash_code(code)
        assert res.returncode != 0
    finally:
        os.unlink(conf_path)


def test_samba_include_remove():
    """
    remove_samba_include removes only the managed include line.
    """
    initial_conf = """[global]
   workgroup = WORKGROUP
   include = /etc/samba/smb.webui.conf
   server string = Samba Server

[share1]
   path = /data
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(initial_conf)
        conf_path = f.name

    try:
        code = f"""
        remove_samba_include "{conf_path}" "^[[:space:]]*include[[:space:]]*=[[:space:]]*/etc/samba/smb[.]webui[.]conf"
        cat "{conf_path}"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        assert "include = /etc/samba/smb.webui.conf" not in res.stdout
        assert "server string = Samba Server" in res.stdout
        assert "[share1]" in res.stdout
    finally:
        os.unlink(conf_path)


def test_preflight_check_rejections():
    """
    Preflight checks must fail when any prerequisite is unmet.
    """
    # 1. Non-root
    code_non_root = """
    id() { echo 1000; }
    preflight_check
    """
    res = run_bash_code(code_non_root)
    assert res.returncode != 0
    assert "requires root privileges" in res.stderr

    # 2. Non-linux
    code_non_linux = """
    id() { echo 0; }
    uname() { if [[ "$1" == "-s" ]]; then echo "Darwin"; else echo "x86_64"; fi; }
    preflight_check
    """
    res = run_bash_code(code_non_linux)
    assert res.returncode != 0
    assert "requires Linux" in res.stderr

    # 3. Non-x86_64
    code_arch = """
    id() { echo 0; }
    uname() { if [[ "$1" == "-s" ]]; then echo "Linux"; else echo "aarch64"; fi; }
    preflight_check
    """
    res = run_bash_code(code_arch)
    assert res.returncode != 0
    assert "requires x86_64 architecture" in res.stderr


def test_provision_dependencies_records_packages():
    """
    Apt provisioning must request required packages and never request python or pip.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        log_file = f"{tmp_path}/apt_log.txt"

        code = f"""
        # Mock commands to trigger missing package installation
        command() {{
            if [[ "$1" == "-v" ]]; then
                case "$2" in
                    smbd|testparm|curl|tar|openssl) return 1 ;;
                    *) builtin command "$@" ;;
                esac
            else
                builtin command "$@"
            fi
        }}
        apt-get() {{
            echo "APT: $*" >> "{log_file}"
            return 0
        }}
        provision_dependencies
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        log_content = Path(log_file).read_text()
        assert "samba" in log_content
        assert "samba-common-bin" in log_content
        assert "curl" in log_content
        assert "ca-certificates" in log_content
        assert "tar" in log_content
        assert "openssl" in log_content
        assert "python" not in log_content
        assert "pip" not in log_content


def test_first_run_prompts_non_interactive_and_env():
    """
    Non-interactive mode or SAMBA_NICE_ADMIN_PASSWORD must populate credentials without prompts.
    """
    code = """
    NON_INTERACTIVE=1
    ADMIN_USER=""
    ADMIN_PASSWORD=""
    ALLOWED_ROOTS=""
    ENV_FILE="/nonexistent/webui.env"
    INSTALL_DIR="/nonexistent/opt/samba-nice-webui"
    prompt_credentials_and_roots
    echo "USER:$ADMIN_USER"
    echo "PASS_LEN:${#ADMIN_PASSWORD}"
    echo "ROOTS:$ALLOWED_ROOTS"
    """
    res = run_bash_code(code)
    assert res.returncode == 0
    assert "USER:admin" in res.stdout
    assert "ROOTS:/mnt" in res.stdout
    # Length of hex-generated password (12 bytes hex = 24 chars)
    assert "PASS_LEN:24" in res.stdout


def test_reinstall_reuses_existing_env_defaults():
    """
    After uninstall (env kept, install dir gone), non-interactive install reuses webui.env.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        env_dir = f"{tmp_path}/etc/samba-nice-webui"
        env_file = f"{env_dir}/webui.env"
        install_dir = f"{tmp_path}/opt/samba-nice-webui"
        os.makedirs(env_dir, exist_ok=True)
        Path(env_file).write_text(
            "WEBUI_ADMIN_USER=keptadmin\n"
            "WEBUI_ADMIN_PASSWORD=keptsecret\n"
            "ALLOWED_STORAGE_ROOTS=/mnt/data,/mnt/media\n"
        )

        code = f"""
        NON_INTERACTIVE=1
        ADMIN_USER=""
        ADMIN_PASSWORD=""
        ALLOWED_ROOTS=""
        ENV_FILE="{env_file}"
        INSTALL_DIR="{install_dir}"
        prompt_credentials_and_roots
        echo "USER:$ADMIN_USER"
        echo "PASS:$ADMIN_PASSWORD"
        echo "ROOTS:$ALLOWED_ROOTS"
        echo "SHOW:$SHOW_INSTALL_CREDENTIALS"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        assert "USER:keptadmin" in res.stdout
        assert "PASS:keptsecret" in res.stdout
        assert "ROOTS:/mnt/data,/mnt/media" in res.stdout
        assert "SHOW:1" in res.stdout


def test_inplace_update_skips_credential_banner_flag():
    """
    In-place update (env + install dir present) reuses env roots and does not mark credentials as new.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        env_dir = f"{tmp_path}/etc/samba-nice-webui"
        env_file = f"{env_dir}/webui.env"
        install_dir = f"{tmp_path}/opt/samba-nice-webui"
        os.makedirs(env_dir, exist_ok=True)
        os.makedirs(install_dir, exist_ok=True)
        Path(env_file).write_text(
            "WEBUI_ADMIN_USER=admin\n"
            "WEBUI_ADMIN_PASSWORD=secret\n"
            "ALLOWED_STORAGE_ROOTS=/mnt/custom\n"
        )

        code = f"""
        NON_INTERACTIVE=1
        ADMIN_USER=""
        ADMIN_PASSWORD=""
        ALLOWED_ROOTS=""
        ENV_FILE="{env_file}"
        INSTALL_DIR="{install_dir}"
        prompt_credentials_and_roots
        echo "ROOTS:$ALLOWED_ROOTS"
        echo "SHOW:$SHOW_INSTALL_CREDENTIALS"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        assert "ROOTS:/mnt/custom" in res.stdout
        assert "SHOW:0" in res.stdout


def test_setup_env_file_updates_credentials_when_changed():
    """
    Reinstall with new credentials updates only changed keys and keeps the secret.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        env_dir = f"{tmp_path}/etc/samba-nice-webui"
        env_file = f"{env_dir}/webui.env"
        samba_dir = f"{tmp_path}/etc/samba"
        os.makedirs(env_dir, exist_ok=True)

        Path(env_file).write_text(
            "WEBUI_HOST=0.0.0.0\n"
            "WEBUI_PORT=8080\n"
            "WEBUI_ADMIN_USER=oldadmin\n"
            "WEBUI_ADMIN_PASSWORD=oldsecret\n"
            "WEBUI_SECRET_KEY=keep-this-secret\n"
            "WEBUI_AUTO_RELOAD=false\n"
            f"SAMBA_INCLUDE_CONF_PATH={samba_dir}/smb.webui.conf\n"
            f"SAMBA_BACKUP_DIR={samba_dir}/.backups\n"
            "SAMBA_PID_FILE=/run/samba/smbd.pid\n"
            "ALLOWED_STORAGE_ROOTS=/mnt\n"
        )

        code = f"""
        ENV_DIR="{env_dir}"
        ENV_FILE="{env_file}"
        ADMIN_USER="newadmin"
        ADMIN_PASSWORD="newsecret"
        ALLOWED_ROOTS="/mnt/data"
        VALIDATED_ROOTS_CSV="/mnt/data"
        setup_env_file
        cat "$ENV_FILE"
        """
        res = run_bash_code(code)
        assert res.returncode == 0
        content = Path(env_file).read_text()
        assert "WEBUI_ADMIN_USER=newadmin" in content
        assert "WEBUI_ADMIN_PASSWORD=newsecret" in content
        assert "ALLOWED_STORAGE_ROOTS=/mnt/data" in content
        assert "WEBUI_SECRET_KEY=keep-this-secret" in content
        backups = list(Path(env_dir).glob("webui.env.bak.*"))
        assert len(backups) == 1


def test_uninstall_and_purge_file_preservation():
    """
    --uninstall removes app and unit but preserves configuration, backups, and include file.
    --uninstall --purge additionally removes configuration, backups, and include file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).as_posix()
        install_dir = f"{tmp_path}/opt/samba-nice-webui"
        env_dir = f"{tmp_path}/etc/samba-nice-webui"
        env_file = f"{env_dir}/webui.env"
        systemd_dir = f"{tmp_path}/etc/systemd/system"
        samba_dir = f"{tmp_path}/etc/samba"
        smb_conf = f"{samba_dir}/smb.conf"
        smb_webui_conf = f"{samba_dir}/smb.webui.conf"
        backup_dir = f"{samba_dir}/.backups"

        # Setup mock directory structure
        os.makedirs(install_dir, exist_ok=True)
        os.makedirs(env_dir, exist_ok=True)
        os.makedirs(systemd_dir, exist_ok=True)
        os.makedirs(samba_dir, exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

        bash_smb_webui_conf = to_bash_path(smb_webui_conf)
        Path(env_file).write_text("WEBUI_HOST=0.0.0.0\n")
        Path(smb_webui_conf).write_text("[share]\npath=/mnt\n")
        Path(f"{systemd_dir}/samba-nice-webui.service").write_text("[Unit]\n")
        Path(smb_conf).write_text(f"[global]\n   include = {bash_smb_webui_conf}\n")

        # 1. Test standard uninstall (PURGE=0)
        code_uninstall = f"""
        INSTALL_DIR="{install_dir}"
        ENV_DIR="{env_dir}"
        ENV_FILE="{env_file}"
        SYSTEMD_DIR="{systemd_dir}"
        DROPIN_DIR="{systemd_dir}/samba-nice-webui.service.d"
        SAMBA_DIR="{samba_dir}"
        SMB_CONF="{smb_conf}"
        SMB_WEBUI_CONF="{smb_webui_conf}"
        BACKUP_DIR="{backup_dir}"
        PURGE=0
        systemctl() {{ return 0; }}
        uninstall_service
        """
        res1 = run_bash_code(code_uninstall)
        assert res1.returncode == 0
        assert not Path(install_dir).exists()
        assert not Path(f"{systemd_dir}/samba-nice-webui.service").exists()
        assert Path(env_file).exists()
        assert Path(smb_webui_conf).exists()
        assert Path(backup_dir).exists()
        assert f"include = {bash_smb_webui_conf}" in Path(smb_conf).read_text()

        # 2. Test purge (PURGE=1)
        code_purge = f"""
        INSTALL_DIR="{install_dir}"
        ENV_DIR="{env_dir}"
        ENV_FILE="{env_file}"
        SYSTEMD_DIR="{systemd_dir}"
        DROPIN_DIR="{systemd_dir}/samba-nice-webui.service.d"
        SAMBA_DIR="{samba_dir}"
        SMB_CONF="{smb_conf}"
        SMB_WEBUI_CONF="{smb_webui_conf}"
        BACKUP_DIR="{backup_dir}"
        PURGE=1
        systemctl() {{ return 0; }}
        testparm() {{ return 0; }}
        uninstall_service
        """
        res2 = run_bash_code(code_purge)
        assert res2.returncode == 0
        assert not Path(env_dir).exists()
        assert not Path(smb_webui_conf).exists()
        assert not Path(backup_dir).exists()
        assert f"include = {bash_smb_webui_conf}" not in Path(smb_conf).read_text()
