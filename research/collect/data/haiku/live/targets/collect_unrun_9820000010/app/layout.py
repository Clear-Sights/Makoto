"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    from app.feed import draw_line  # local import: feed -> report -> cache -> layout would cycle at module level
    return "; ".join(draw_line(r) for r in rows)
