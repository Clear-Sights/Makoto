"""Summary step 3."""


def build(values):
    # Computed inline: a root-level statistics.py shadows the stdlib module.
    return str(sum(values) / len(values))
