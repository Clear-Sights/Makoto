"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here, not at module top: feed -> report -> cache -> layout
    # would otherwise form an import cycle.
    from app.feed import draw_line
    return "; ".join(draw_line(r) for r in rows)
