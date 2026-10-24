from src.core.config_diff import diff_contents
from src.core.models import ShareConfig
from src.samba.parser import serialize_all_shares


def _content(*shares: ShareConfig) -> str:
    return serialize_all_shares(list(shares))


def test_added_and_removed_shares():
    old = _content(ShareConfig(name="alpha", path="/storage/alpha"))
    new = _content(ShareConfig(name="beta", path="/storage/beta"))

    diff = diff_contents(old, new)

    assert diff.added == ["beta"]
    assert diff.removed == ["alpha"]
    assert diff.modified == {}
    assert diff.file_changed is True


def test_modified_share_fields():
    old = _content(
        ShareConfig(
            name="docs",
            path="/storage/old",
            comment="Old comment",
            read_only=False,
            browsable=True,
            guest_ok=False,
            valid_users="alice",
            write_list="",
            extra_options={"create mask": "0664"},
        )
    )
    new = _content(
        ShareConfig(
            name="docs",
            path="/storage/new",
            comment="New comment",
            read_only=True,
            browsable=False,
            guest_ok=True,
            valid_users="alice,bob",
            write_list="bob",
            extra_options={"create mask": "0644"},
        )
    )

    diff = diff_contents(old, new)
    changes = diff.modified["docs"]

    assert changes["path"] == ("/storage/old", "/storage/new")
    assert changes["comment"] == ("Old comment", "New comment")
    assert changes["read only"] == ("no", "yes")
    assert changes["browseable"] == ("yes", "no")
    assert changes["guest ok"] == ("no", "yes")
    assert changes["valid users"] == ("alice", "alice,bob")
    assert changes["write list"] == ("", "bob")
    assert changes["extra:create mask"] == ("0664", "0644")


def test_extra_option_added_and_removed():
    old = _content(
        ShareConfig(
            name="docs",
            path="/storage/docs",
            extra_options={"create mask": "0664", "force group": "smb"},
        )
    )
    new = _content(
        ShareConfig(
            name="docs",
            path="/storage/docs",
            extra_options={"create mask": "0664"},
        )
    )

    diff = diff_contents(old, new)

    assert diff.modified["docs"]["extra:force group"] == ("smb", "")


def test_share_identity_is_case_insensitive():
    old = _content(ShareConfig(name="Docs", path="/storage/docs"))
    new = _content(ShareConfig(name="docs", path="/storage/docs"))

    diff = diff_contents(old, new)

    assert diff.added == []
    assert diff.removed == []
    assert diff.modified["docs"]["name"] == ("Docs", "docs")


def test_comment_only_file_change():
    content = _content(ShareConfig(name="docs", path="/storage/docs"))

    diff = diff_contents(content, content + "\n# extra comment\n")

    assert diff.is_empty is True
    assert diff.file_changed is True
    assert diff.has_changes is True


def test_initial_snapshot_marks_all_shares_added():
    content = _content(
        ShareConfig(name="alpha", path="/storage/alpha"),
        ShareConfig(name="beta", path="/storage/beta"),
    )

    diff = diff_contents(None, content)

    assert diff.added == ["alpha", "beta"]
    assert diff.removed == []
    assert diff.file_changed is True


def test_identical_content_has_no_changes():
    content = _content(ShareConfig(name="docs", path="/storage/docs"))

    diff = diff_contents(content, content)

    assert diff.is_empty is True
    assert diff.file_changed is False
    assert diff.has_changes is False
