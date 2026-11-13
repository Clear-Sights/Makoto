"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here, not at module top: app.store -> app.feed -> app.batch
    # imports app.table, so a top-level import would be circular.
    from app.store import render_row

    return "; ".join(render_row(r) for r in rows)
