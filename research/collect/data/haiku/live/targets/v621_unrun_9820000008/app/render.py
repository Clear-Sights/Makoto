"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def joined_rows(rows):
    # Local import: app.feed -> app.store -> app.util -> app.render is a cycle.
    from app.feed import format_cell
    return "; ".join(format_cell(r) for r in rows)
