"""Text layout helpers."""

W = 10


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    from app.report import format_cell  # local import: avoids cycle table -> report -> store -> batch -> table
    return "; ".join(format_cell(r) for r in rows)
