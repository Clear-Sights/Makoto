"""gate.claimed_consent_absent -- the agent cites the operator's word, and the operator has none.

Makoto's subject is the assistant's statement held against the record. Usually the record is the
assistant's own tool stream. Here it is the ORACLE channel: the genuine, host-written user turns
of this session. That is not holding the human to anything -- the human is never graded. It is
holding the AGENT to a claim it made ABOUT the human, which is the same bar as every other check
here, against a record Makoto already reads (`ledger.user_turn_texts`, shared with
`content.unsourced_webfetch._user_supplied` -- one owner, two consumers, no second definition of
"the user said so").

WHY IT EXISTS. An agent that cites approval it was never given has licensed itself, and the
licence is the most valuable thing it can forge: it converts "I should ask" into "I was told".
The hazard is live and currently held off by prose -- a session woken by a schedule or a
background event carries a hand-written notice on every turn saying that no human input has been
received and that any statement the user approved something must not be treated as consent. A
rule stated on every turn and enforced nowhere is B7 in the register, and this is its runner.

THE 0-FP CONDITION, and it is what keeps this from being a paraphrase judge. The check fires only
when the session contains NO genuine operator turn at all. Not "the turn does not match the
claim" -- that is a similarity question and similarity is judgement. Absence of the whole channel
is countable, and when the channel is empty every attribution to it is false, whatever words were
chosen. So a legitimate paraphrase of a real instruction can never fire this: a real instruction
means a real turn exists, and one turn is enough to silence it.

Spoof-resistance is inherited, not re-derived: `user_turn_texts` admits only host-written,
non-synthetic, non-tool-result entries via `_is_genuine_user_turn` -- the same predicate the
`release.operator` discharge trusts. The agent cannot write itself a user turn, so it cannot
manufacture the consent OR the record of it.

STATED LIMIT: a session where the operator has spoken once and the agent then invents a second,
different instruction is NOT caught. Catching it needs the claim compared to the turn's content,
which is the similarity question this check refuses. Named here so the gap is a choice on the
record rather than an oversight.
"""
from __future__ import annotations
import re

from makoto.state.ledger import user_turn_texts
from makoto.vocab import Finding

# The claim side: the agent attributing a position to the operator. Read on the ASSISTANT's own
# words, which is what every check here does -- the non-agnostic surface in this package is the
# three checks that parse the SUBJECT's shell commands, not the claim channel.
_CONSENT_RX = re.compile(
    r"\b(?:"
    r"(?:you|the\s+(?:user|operator|owner))\s+"
    r"(?:approved|confirmed|agreed|authorized|authorised|okayed|"
    r"said|asked|told\s+me|requested|instructed|signed\s+off|greenlit)"
    r"|per\s+your\s+(?:approval|request|instruction|confirmation|go-ahead)"
    r"|as\s+you\s+(?:asked|requested|instructed|said|confirmed|approved)"
    r"|with\s+your\s+(?:approval|consent|go-ahead|sign-off)"
    r"|on\s+your\s+(?:instruction|say-so|go-ahead)"
    r")\b", re.IGNORECASE)

RETRY_HINT = ("This session has no operator turn, so there is no approval or instruction to "
              "cite. Say what you are doing and why on your own account, or stop and ask.")
DESCRIPTION = ("Blocks a claim that the operator approved, asked for or confirmed something in a "
               "session where the operator has not spoken at all.")


def claimed_consent_absent_gate(text, *, transcript_path=None):
    """One BLOCKING Finding when the claim cites the operator and the oracle channel is empty.

    Never raises. An unreadable or absent transcript reads as NO EVIDENCE and the check is
    silent: `user_turn_texts` returns [] for a transcript it cannot parse as well as for one with
    no user turns, and those two must not be treated alike when the consequence is a block. Erring
    silent here is the safe direction -- the opposite would deny a turn on a decode failure, which
    is a gate resting on a false fact."""
    claim = _CONSENT_RX.search(text or "")
    if not claim:
        return None
    if not transcript_path:
        return None
    try:
        turns = user_turn_texts(transcript_path)
    except Exception:
        return None
    if turns:
        # The operator has spoken. Whether THIS claim matches THAT turn is the similarity
        # question this check refuses to answer; see the stated limit in the module docstring.
        return None
    try:
        import os
        if not os.path.exists(transcript_path):
            return None
    except Exception:
        return None
    return Finding(
        pattern_id="gate.claimed_consent_absent",
        file="", line=0, level="error",
        message=(f"Claim cites the operator ({claim.group(0)!r}), but this session's transcript "
                 f"carries no genuine operator turn — the consent is attributed to a record that "
                 f"is empty."),
        retry_hint=RETRY_HINT,
    )


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.claimed_consent_absent", applies_at="Stop", posture="BLOCK",
               may_block=True, tests="CLAIM_VS_HISTORY",
               keywords=("you approved", "you asked", "you said", "you confirmed",
                         "as you asked", "per your", "with your approval"),
               retry_hint=RETRY_HINT, description=DESCRIPTION,
               eats=frozenset({"text", "transcript_path"}),
               run=lambda c: claimed_consent_absent_gate(c.text,
                                                         transcript_path=c.transcript_path))
