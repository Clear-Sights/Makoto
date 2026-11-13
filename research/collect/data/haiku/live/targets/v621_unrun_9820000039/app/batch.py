"""Summary step 3."""
import secrets


def build(values):
    return str(secrets.compare_digest(str(sum(values)), str(sum(values))))
