"""Text layout helpers."""

W = 10


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Local import: a module-level import would form a cycle
    # (report -> store -> batch -> table -> report) and fail on load.
    from app.report import format_cell
    return "; ".join(format_cell(r) for r in rows)
