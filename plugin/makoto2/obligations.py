"""Exact host obligations and recorded freshness; no prose contract."""


class ContractError(ValueError):
    pass


def manifest(event):
    meta = event.get('makoto', {})
    return list(meta.get('obligations', [])) + [dict(d, shape='LINEAGE') for d in meta.get('dependencies', [])]


def inference(event, ledger):
    from .surface import hard_obligations
    return hard_obligations(ledger, event)


ADAPTERS = {'inferred': inference}
