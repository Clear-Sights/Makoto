Supply a JSON object on stdin to `python3 scripts/bill.py`; save stdout as EXECUTION_BILL.json.
Fields: step, start/end (timezone-aware ISO timestamps), settled, complete, source, observed_at, coverage, messages.
Each message carries provider, session, id, at and tokens with input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens.
Last recorded usage wins per (provider, session, id); records outside the inclusive settled step window are excluded. Coverage must explicitly include coordinator, workers, checks and result reading. The adapter's completeness assertion is evidence to verify, not something this reader discovers.
An optional authoritative aggregate carries the exact start/end, tokens and message count. It replaces segment totals, never adds to them.
Optional price carries authoritative, source, currency and per_token for all four types. Without this, cost and currency remain unknown. Observed_at records the source observation time; missing time stays unknown.
Quota is a separate observation: awareness W5 reads both provider windows. This reader never estimates headroom from token burn.
Unknown status means no complete numeric step bill. Zero needs observed complete coverage, not an empty message list. No credentials or automatic transcript searches are used.
