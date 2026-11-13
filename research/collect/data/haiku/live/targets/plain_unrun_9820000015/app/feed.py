"""Summary step 3."""
import textwrap


def build(values):
    return str(textwrap.shorten(' '.join(map(str, values)), 9))
