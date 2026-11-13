# AMEND_1: the round runs on CLI 2.1.323. Committed before any usable run; never edited after.

- **Finding:** the machine's Claude Code CLI is now 2.1.323. Version 2.1.322, which every earlier round used, is no longer installed.
- **Effect on the first kill test:** the harness accepts only its pinned version, so it marked those runs unusable. Its 4 calls, 0.025 USD, are kept in `data/kill/`.
- **Change:** `harness/live_v621.py` pins `CLI = '2.1.323'`. Every arm of this round runs on it, so the arms stay comparable with each other.
- **Limit:** this round's numbers are not compared with earlier rounds' numbers (CLAUDE.md rule 3 of the Tiller protocol: never compare across settings).
- **Unchanged:** everything else in RULES.md.
