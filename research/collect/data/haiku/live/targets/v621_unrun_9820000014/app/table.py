"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: store -> feed -> batch -> table would be circular at module level.
    from app.store import render_row
    return "; ".join(render_row(r) for r in rows)
