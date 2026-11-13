"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    # Imported here: a module-level import would form a cycle
    # (feed -> store -> batch -> sheet -> feed) and fail on load.
    from app.feed import render_row
    return '; '.join(render_row(r) for r in rows)
