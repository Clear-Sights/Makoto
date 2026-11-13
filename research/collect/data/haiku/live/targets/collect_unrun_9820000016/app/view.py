"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def joined_rows(rows):
    # Imported here: store -> index -> util -> view would be circular at module level.
    from app.store import render_row
    return "; ".join(render_row(r) for r in rows)
