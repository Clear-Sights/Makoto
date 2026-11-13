"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    from app.feed import draw_line  # local import avoids feed->report->cache->layout cycle
    return "; ".join(draw_line(r) for r in rows)
