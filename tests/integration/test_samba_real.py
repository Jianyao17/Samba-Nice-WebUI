"""Integration test dengan smbd sungguhan.

Setiap perubahan lewat LinuxHostSambaBackend diverifikasi dari sisi client SMB
(smbclient), bukan dari file konfigurasi saja.
"""

import os

from src.core.models import ShareConfig


def make_share(storage, name: str) -> ShareConfig:
    path = storage / name
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o777)
    return ShareConfig(name=name, path=str(path), guest_ok=True, read_only=False)


def test_smbd_daemon_is_running(backend, samba_server):
    status = backend.get_status()

    assert status.is_running is True
    assert status.pid == int(samba_server.pid_file.read_text().strip())


def test_new_share_is_served_by_smbd(backend, samba_server, smb_client, tmp_path):
    share = make_share(samba_server.storage, "docs")

    result = backend.save_share(share)
    assert result.is_valid, result.message
    assert smb_client.wait_until(lambda: "docs" in smb_client.visible_shares())

    # Client bisa menulis file ke share, dan file itu muncul di disk
    payload = tmp_path / "hello.txt"
    payload.write_text("hello samba")
    assert smb_client.upload("docs", payload, "hello.txt")
    assert (samba_server.storage / "docs" / "hello.txt").read_text() == "hello samba"


def test_update_to_read_only_is_enforced_after_reload(backend, samba_server, smb_client, tmp_path):
    share = make_share(samba_server.storage, "docs")
    assert backend.save_share(share).is_valid
    assert smb_client.wait_until(lambda: "docs" in smb_client.visible_shares())

    payload = tmp_path / "file.txt"
    payload.write_text("data")
    assert smb_client.upload("docs", payload, "before.txt")

    # Setelah diubah menjadi read-only dan smbd di-reload, upload harus ditolak
    updated = share.model_copy(update={"read_only": True})
    assert backend.save_share(updated, original_name="docs").is_valid
    assert smb_client.wait_until(lambda: not smb_client.upload("docs", payload, "after.txt"))
    assert not (samba_server.storage / "docs" / "after.txt").exists()


def test_rename_share_changes_what_clients_see(backend, samba_server, smb_client):
    share = make_share(samba_server.storage, "docs")
    assert backend.save_share(share).is_valid
    assert smb_client.wait_until(lambda: smb_client.visible_shares() == {"docs"})

    renamed = share.model_copy(update={"name": "archive"})
    assert backend.save_share(renamed, original_name="docs").is_valid
    assert smb_client.wait_until(lambda: smb_client.visible_shares() == {"archive"})


def test_deleted_share_disappears_from_smbd(backend, samba_server, smb_client):
    share = make_share(samba_server.storage, "docs")
    assert backend.save_share(share).is_valid
    assert smb_client.wait_until(lambda: "docs" in smb_client.visible_shares())

    assert backend.delete_share("docs") is True
    assert smb_client.wait_until(lambda: "docs" not in smb_client.visible_shares())
    assert backend.delete_share("docs") is False


def test_duplicate_share_is_rejected_and_smbd_is_untouched(backend, samba_server, smb_client):
    share = make_share(samba_server.storage, "docs")
    assert backend.save_share(share).is_valid
    assert smb_client.wait_until(lambda: "docs" in smb_client.visible_shares())

    other = make_share(samba_server.storage, "other")
    duplicate = other.model_copy(update={"name": "docs"})
    assert backend.save_share(duplicate).is_valid is False

    assert backend.get_share("docs").path == str(share.path)
    assert smb_client.visible_shares() == {"docs"}
