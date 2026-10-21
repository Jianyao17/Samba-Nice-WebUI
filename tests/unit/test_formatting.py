from src.core.formatting import format_size

def test_format_size_bytes():
    assert format_size(0) == "0 B"
    assert format_size(1) == "1 B"
    assert format_size(1023) == "1023 B"

def test_format_size_kilobytes():
    assert format_size(1024) == "1.0 KB"
    assert format_size(1536) == "1.5 KB"

def test_format_size_megabytes_and_beyond():
    assert format_size(1024 ** 2) == "1.0 MB"
    assert format_size(int(5.5 * 1024 ** 2)) == "5.5 MB"
    assert format_size(1024 ** 3) == "1.0 GB"
    assert format_size(1024 ** 4) == "1.0 TB"
    assert format_size(1024 ** 5) == "1.0 PB"

def test_format_size_does_not_round_into_next_unit():
    # 1023.99 KB must render as 1.0 MB, not "1024.0 KB"
    assert format_size(1024 * 1024 - 1) == "1.0 MB"

def test_format_size_handles_invalid_values():
    assert format_size(None) == "—"
    assert format_size(-5) == "—"
    assert format_size("not-a-number") == "—"
