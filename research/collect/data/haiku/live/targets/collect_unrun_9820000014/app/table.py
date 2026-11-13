"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Local import: a module-level import would form a cycle
    # (store -> feed -> batch -> table -> store).
    from app.store import render_row
    return "; ".join(render_row(r) for r in rows)
