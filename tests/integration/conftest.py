"""Fixture untuk integration test dengan smbd sungguhan.

Fixture ini menjalankan daemon smbd asli di folder sementara, lalu mengarahkan
LinuxHostSambaBackend ke konfigurasi tersebut. Test di-skip otomatis bila
smbd/smbclient tidak tersedia (misalnya di Windows), sehingga `uv run pytest`
tetap berjalan di mesin mana pun. Untuk hasil lengkap, jalankan lewat Docker
(lihat Dockerfile.test).
"""

import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.core.backup import BackupManager
from src.samba.linux_backend import LinuxHostSambaBackend


@dataclass
class SambaServer:
    port: int
    storage: Path
    include_conf: Path
    smb_conf: Path
    pid_file: Path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _write_smb_conf(root: Path, port: int) -> Path:
    # 1. Semua path state Samba diarahkan ke folder sementara agar tidak menyentuh sistem
    dirs = {name: root / name for name in ["run", "lock", "state", "cache", "private", "ncalrpc", "log"]}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    include_conf = root / "etc" / "smb.webui.conf"
    include_conf.parent.mkdir(parents=True, exist_ok=True)
    include_conf.write_text("", encoding="utf-8")

    # 2. Baris `include` harus menjadi baris terakhir di [global]; baris setelahnya
    #    akan terbawa ke section share yang di-include.
    smb_conf = root / "smb.conf"
    smb_conf.write_text(
        f"""[global]
   workgroup = WORKGROUP
   server role = standalone server
   security = user
   map to guest = Bad User
   smb ports = {port}
   disable netbios = yes
   load printers = no
   server min protocol = SMB2
   pid directory = {dirs['run']}
   lock directory = {dirs['lock']}
   state directory = {dirs['state']}
   cache directory = {dirs['cache']}
   private dir = {dirs['private']}
   ncalrpc dir = {dirs['ncalrpc']}
   log file = {dirs['log']}/%m
   log level = 1
   include = {include_conf}
""",
        encoding="utf-8",
    )
    return smb_conf


class SambaClient:
    """Klien kecil untuk memeriksa hasil dari sisi client SMB sungguhan."""

    def __init__(self, port: int):
        self.port = port

    def _smbclient(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["smbclient", *args, "-N", "-p", str(self.port)],
            capture_output=True,
            text=True,
            check=False,
        )

    def is_listening(self) -> bool:
        return self._smbclient("-L", "127.0.0.1", "-g").returncode == 0

    def visible_shares(self) -> set[str]:
        """Nama share (tipe Disk) yang benar-benar terlihat oleh client."""
        output = self._smbclient("-L", "127.0.0.1", "-g").stdout
        return {line.split("|")[1] for line in output.splitlines() if line.startswith("Disk|")}

    def upload(self, share: str, local_file: Path, remote_name: str) -> bool:
        """Coba upload file ke share. Mengembalikan True bila berhasil."""
        result = self._smbclient(f"//127.0.0.1/{share}", "-c", f"put {local_file} {remote_name}")
        return result.returncode == 0

    def wait_until(self, check, timeout: float = 10) -> bool:
        """Polling sampai kondisi terpenuhi; reload SIGHUP berjalan asinkron."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if check():
                return True
            time.sleep(0.2)
        return False


@pytest.fixture(scope="session")
def smb_client(samba_server) -> SambaClient:
    return SambaClient(samba_server.port)


@pytest.fixture(scope="session")
def samba_server():
    # 1. Lewati bila binary Samba tidak ada (mis. Windows atau host tanpa Samba)
    if shutil.which("smbd") is None or shutil.which("smbclient") is None:
        pytest.skip("smbd/smbclient tidak tersedia; jalankan integration test lewat Dockerfile.test")

    # 2. Siapkan konfigurasi, storage, dan start smbd dalam mode daemon.
    #    Folder harus bisa ditelusuri user guest (nobody), jadi tidak memakai
    #    tmp_path_factory (yang membuat direktori bermode 0700).
    root = Path(tempfile.mkdtemp(prefix="samba_it_"))
    root.chmod(0o755)
    port = _free_port()
    smb_conf = _write_smb_conf(root, port)
    pid_file = root / "run" / "smbd.pid"
    storage = root / "storage"
    storage.mkdir()

    subprocess.run(["smbd", "-s", str(smb_conf), "-D"], check=True)

    # 3. Tunggu sampai smbd benar-benar menerima koneksi
    deadline = time.monotonic() + 15
    client = SambaClient(port)
    while not (client.is_listening() and pid_file.exists()):
        if time.monotonic() > deadline:
            log_dir = root / "log"
            logs = "\n".join(p.read_text(errors="replace") for p in log_dir.glob("*"))
            pytest.fail(f"smbd gagal start pada port {port}.\n{logs}")
        time.sleep(0.2)

    yield SambaServer(
        port=port,
        storage=storage,
        include_conf=root / "etc" / "smb.webui.conf",
        smb_conf=smb_conf,
        pid_file=pid_file,
    )

    # 4. Hentikan smbd dan bersihkan folder kerja setelah semua test selesai
    pid = int(pid_file.read_text().strip())
    os.kill(pid, signal.SIGTERM)
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def backend(samba_server, smb_client, tmp_path):
    # 1. Kosongkan konfigurasi share agar setiap test mulai dari kondisi bersih
    samba_server.include_conf.write_text("", encoding="utf-8")
    backup_mgr = BackupManager(
        backup_dir=tmp_path / "backups",
        include_conf_path=samba_server.include_conf,
    )
    samba = LinuxHostSambaBackend(
        include_conf_path=samba_server.include_conf,
        pid_file=samba_server.pid_file,
        backup_manager=backup_mgr,
    )
    samba.reload_service()

    # 2. Tunggu sampai smbd benar-benar memuat konfigurasi kosong
    assert smb_client.wait_until(lambda: smb_client.visible_shares() == set())
    return samba
