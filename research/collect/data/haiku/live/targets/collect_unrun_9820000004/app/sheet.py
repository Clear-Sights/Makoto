"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    # Imported here: app.feed -> app.store -> app.batch -> app.sheet would
    # otherwise form a circular import at module load time.
    from app.feed import render_row
    return '; '.join(render_row(r) for r in rows)
