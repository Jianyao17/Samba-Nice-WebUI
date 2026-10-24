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


def test_parse_normalizes_option_keys_and_synonyms():
    # 1. Mixed case, repeated spaces, and Samba synonyms must map to one key
    raw_conf = """
    [Media]
        Path = /storage/media
        Comment = Media files
        Read Only = Yes
        Browseable = No
        Public = Yes
        Writeable = Yes
        Veto  Files = /tmp/*
    """

    shares = parse_conf_content(raw_conf)
    assert len(shares) == 1
    media = shares[0]

    # 2. 'writeable = yes' is the inverted synonym of 'read only' and wins
    assert media.path == "/storage/media"
    assert media.read_only is False
    assert media.browsable is False
    assert media.guest_ok is True
    assert media.extra_options == {"veto files": "/tmp/*"}


def test_parse_merges_duplicate_sections_case_insensitively():
    # 1. Manual duplicate sections differing only by case must collapse
    raw_conf = """
    [Data]
        path = /storage/data
        comment = First
        guest ok = no

    [other]
        path = /storage/other

    [data]
        comment = Second
        read only = yes
    """

    shares = parse_conf_content(raw_conf)

    # 2. One entry per share name, with the first spelling kept
    assert [share.name for share in shares] == ["Data", "other"]
    data = shares[0]
    assert data.path == "/storage/data"
    assert data.comment == "Second"
    assert data.read_only is True
    assert data.guest_ok is False


def test_duplicate_sections_do_not_survive_round_trip():
    from src.samba.parser import serialize_all_shares

    # 1. Parse a hand-edited file with a duplicated section
    raw_conf = """
    [data]
        path = /storage/data
        comment = First

    [DATA]
        comment = Second
    """

    shares = parse_conf_content(raw_conf)

    # 2. Rewriting the file produces exactly one section
    serialized = serialize_all_shares(shares)
    assert serialized.lower().count("[data]") == 1
    assert "comment = Second" in serialized
