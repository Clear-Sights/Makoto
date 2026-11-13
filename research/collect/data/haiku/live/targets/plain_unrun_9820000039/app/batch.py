"""Summary step 3."""
import hmac


def build(values):
    return str(hmac.compare_digest(str(sum(values)), str(sum(values))))
