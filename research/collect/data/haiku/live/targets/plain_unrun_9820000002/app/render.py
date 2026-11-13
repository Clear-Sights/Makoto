"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here: report -> util -> index -> render would be circular at module load.
    from app.report import show_item
    return "; ".join(show_item(r) for r in rows)
