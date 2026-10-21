"""Shared formatting helpers for human-readable values."""

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")

def format_size(size_bytes: int | float | None) -> str:
    """
    Format a byte count into a human-readable size string.

    Scales automatically between B, KB, MB, GB, TB and PB so large files no
    longer show as an ever-growing KB value.

    Examples:
        0            -> "0 B"
        512          -> "512 B"
        2048         -> "2.0 KB"
        5_242_880    -> "5.0 MB"
        3_221_225_472 -> "3.0 GB"
    """
    if size_bytes is None:
        return "—"
    try:
        size = float(size_bytes)
    except (TypeError, ValueError):
        return "—"

    if size < 0:
        return "—"
    if size < 1024:
        return f"{int(size)} B"

    unit_index = 1
    size /= 1024
    while size >= 1024 and unit_index < len(_UNITS) - 1:
        size /= 1024
        unit_index += 1

    # Guard against rounding up into the next unit (e.g. 1023.99 KB -> 1024.0 KB)
    if round(size, 1) >= 1024 and unit_index < len(_UNITS) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.1f} {_UNITS[unit_index]}"
