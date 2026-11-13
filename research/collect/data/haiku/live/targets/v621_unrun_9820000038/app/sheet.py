"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: app.cache -> app.index -> app.batch imports app.sheet,
    # so a top-level import would be circular.
    from app.cache import format_cell
    return "; ".join(format_cell(r) for r in rows)
