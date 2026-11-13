"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Local import: a top-level import would cycle (sheet -> cache -> index -> batch -> sheet).
    from app.cache import format_cell
    return "; ".join(format_cell(r) for r in rows)
