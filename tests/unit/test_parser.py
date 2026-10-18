import pytest
from pathlib import Path

from src.core.models import ShareConfig
from src.samba.parser import (
    parse_conf_content,
    sanitize_share_name,
    serialize_share,
)


def test_sanitize_share_name():
    # 1. Clean valid names
    assert sanitize_share_name("my_share") == "my_share"
    assert sanitize_share_name("Data-2026") == "Data-2026"

    # 2. Reject empty or invalid names
    with pytest.raises(ValueError):
        sanitize_share_name("   ")

    # 3. Reject reserved Samba names
    with pytest.raises(ValueError):
        sanitize_share_name("global")

    with pytest.raises(ValueError):
        sanitize_share_name("homes")


def test_serialize_and_parse_share():
    # 1. Create test share config
    share = ShareConfig(
        name="media",
        path="/storage/media",
        comment="Media streaming directory",
        read_only=True,
        browsable=True,
        guest_ok=False,
        valid_users="alice, bob",
        write_list="alice"
    )

    # 2. Serialize to Samba INI string
    serialized = serialize_share(share)
    assert "[media]" in serialized
    assert "path = /storage/media" in serialized
    assert "read only = yes" in serialized
    assert "browsable = yes" in serialized
    assert "guest ok = no" in serialized
    assert "valid users = alice, bob" in serialized
    assert "write list = alice" in serialized

    # 3. Parse serialized string back into ShareConfig
    shares = parse_conf_content(serialized, filename="media.conf")
    assert len(shares) == 1
    parsed = shares[0]

    assert parsed.name == "media"
    assert parsed.path == "/storage/media"
    assert parsed.comment == "Media streaming directory"
    assert parsed.read_only is True
    assert parsed.browsable is True
    assert parsed.guest_ok is False
    assert parsed.valid_users == "alice, bob"
    assert parsed.write_list == "alice"


def test_parse_comments_and_global_exclusion():
    raw_conf = """
    # Global parameters should be ignored by share parser
    [global]
        workgroup = WORKGROUP
        security = user

    ; Commented line
    [public]
        path = /storage/public
        comment = Public files
        guest ok = yes
        read only = no
    """

    shares = parse_conf_content(raw_conf)
    assert len(shares) == 1
    assert shares[0].name == "public"
    assert shares[0].path == "/storage/public"
    assert shares[0].guest_ok is True
    assert shares[0].read_only is False


def test_serialize_all_shares():
    from src.samba.parser import serialize_all_shares

    s1 = ShareConfig(name="share1", path="/storage/share1", comment="First Share")
    s2 = ShareConfig(name="share2", path="/storage/share2", comment="Second Share", read_only=True)

    content = serialize_all_shares([s1, s2])
    assert "[share1]" in content
    assert "[share2]" in content
    assert "Samba-Nice-WebUI Managed Shares" in content

    parsed = parse_conf_content(content)
    assert len(parsed) == 2
    assert parsed[0].name == "share1"
    assert parsed[1].name == "share2"
    assert parsed[1].read_only is True
