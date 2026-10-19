from src.core.smb_address import (
    DEFAULT_SMB_PORT,
    build_smb_uri,
    build_unc_path,
    normalize_smb_host,
    normalize_smb_port,
)


def test_default_smb_uri_omits_port():
    # 1. The standard SMB port is not repeated in the URI
    assert build_smb_uri("nas.local", "public") == "smb://nas.local/public"


def test_custom_smb_port_is_included():
    # 1. Non-standard ports must be visible to the client
    assert build_smb_uri("localhost", "public", 1445) == "smb://localhost:1445/public"


def test_smb_uri_encodes_share_name():
    # 1. Share names are URL-encoded even if the parser usually sanitizes them
    assert build_smb_uri("nas.local", "my share") == "smb://nas.local/my%20share"


def test_smb_uri_supports_ipv6_host():
    # 1. IPv6 literals need brackets inside a URI
    assert build_smb_uri("fe80::1", "public") == "smb://[fe80::1]/public"
    assert normalize_smb_host("[fe80::1]") == "fe80::1"


def test_smb_host_normalization():
    # 1. Accept values copied as an SMB URL and strip trailing slashes
    assert normalize_smb_host("smb://nas.local/") == "nas.local"
    assert normalize_smb_host("  nas.local  ") == "nas.local"
    assert normalize_smb_host("") == "localhost"


def test_unc_path_for_windows_clients():
    # 1. Standard hosts render as a Windows UNC path
    assert build_unc_path("nas.local", "public") == "\\\\nas.local\\public"


def test_unc_path_rejects_unrepresentable_hosts():
    # 1. IPv6 literals and missing share names cannot be a plain UNC path
    assert build_unc_path("fe80::1", "public") == ""
    assert build_unc_path("nas.local", "") == ""


def test_invalid_ports_fall_back_to_standard_port():
    # 1. Invalid values never produce a malformed SMB URI
    assert normalize_smb_port(None) == DEFAULT_SMB_PORT
    assert normalize_smb_port(0) == DEFAULT_SMB_PORT
    assert normalize_smb_port(70000) == DEFAULT_SMB_PORT
    assert normalize_smb_port(1445) == 1445
