"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def joined_rows(rows):
    # Imported here, not at module top: store -> feed -> batch imports
    # this module, so a top-level import would form a cycle.
    from app.store import draw_line
    return "; ".join(draw_line(r) for r in rows)
