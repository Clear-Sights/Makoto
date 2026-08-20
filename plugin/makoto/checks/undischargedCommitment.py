from __future__ import annotations
import re
from typing import Optional
from makoto.checks import normalize_path
from makoto.vocab import Finding
from makoto.vocab import (
    _NEGATION_RX, _UNIVERSAL_DONE_RX, _SENTENCE_SPLIT_RX, _ADV_FORWARD_RX, _ENUM_BEFORE_HEAD_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.kit import DISCHARGE_EATS, _discharged, _path_components, claim_vs_ledger_predicate


# A version/variant rename suffix on a basename stem: parser_v2, config_old, handler-final, foo_copy.
_ADV_RENAME_SUFFIX_RX = re.compile(r"(?:[_-](?:v?\d+|new|old|final|copy|orig|backup|bak|tmp|temp))+$", re.I)


def _adv_stem_core(basename: str):
    """(stem, core, ext): the basename minus extension, that stem minus a trailing rename suffix,
    and the extension itself (leading dot; "" when there is no dot).

    The dot rule is deliberately NOT os.path.splitext's: a dotfile (".bashrc") is all-extension
    with an empty stem, which is what the same-file-type comparison below wants."""
    cut = basename.rfind(".")
    stem, ext = (basename[:cut], basename[cut:]) if cut >= 0 else (basename, "")
    return stem, _ADV_RENAME_SUFFIX_RX.sub("", stem), ext


def _adv_relocated_discharge(commit_loc: str, touched_keys) -> bool:
    """Advance-LOCAL relocation tolerance: True iff a touched key looks like a RENAME of the open
    commitment — SAME parent dir, SAME extension, and one basename stem is the version/variant of
    the other (parser.py -> parser_v2.py). This re-derives a discharge that _discharged's
    separator-boundary suffix-match correctly misses for a moved path, WITHOUT loosening
    _discharged itself (completion + dropped share it). It preserves the fakeexcuse firewall:
    auth.py vs auth_helper.py is NOT a rename (`_helper` is not a version token), so it stays
    undischarged and the gate still fires. Gated behind the open-commitment loop; never broadens
    a genuinely-dropped commitment (no rename-touch -> False -> the TP still fires)."""
    c_comps = _path_components(commit_loc)
    if not c_comps:
        return False
    c_stem, c_core, c_ext = _adv_stem_core(c_comps[-1])
    for k in touched_keys or ():
        k_comps = _path_components(k)
        if not k_comps:
            continue
        k_stem, k_core, k_ext = _adv_stem_core(k_comps[-1])
        if k_ext.lower() != c_ext.lower():
            continue                                  # different file type -> not a rename
        if c_comps[-2:-1] != k_comps[-2:-1]:          # parent-dir component, or [] when top-level
            continue                                  # moved out of dir -> not a same-dir rename
        if c_core and k_core and c_core == k_core and (c_stem != k_stem or c_core != c_stem):
            return True                               # same stem family, one is the renamed variant
    return False


def _advance_signal(text: str) -> bool:
    """True iff `text` makes a universal completion claim — a HEAD quantifier ("all",
    "everything", "the whole thing") binding a (negation-guarded, non-forward, non-code) done-
    word through function words only.

    This is the only advance shape that yields a VERIFIABLE contradiction against an
    undischarged commitment, and the head-vs-determiner split is the 'make it clearer, not
    timid' fix distilled from a real-session corpus. A determiner ("all four phases", "every
    variant tested"), a scoped done ("the design is complete"), an enumerated claim ("all 5 of
    5"), a forward frame ("once everything is done"), or a done-word quoted from code all fail
    open (the keystone) — none of them claims the WHOLE task is done."""
    if not text:
        return False
    spans = _code_spans(text)
    for m in _UNIVERSAL_DONE_RX.finditer(text):
        a = m.start()
        if any(s <= a < e for s, e in spans):
            continue                                  # done-word quoted from code, not prose
        if _ENUM_BEFORE_HEAD_RX.search(text[max(0, a - 24):a]):
            continue                                  # "A-F all built" -> enumerated scope, bounded
        pre = text[max(0, a - 50):a]
        clause = _SENTENCE_SPLIT_RX.split(pre)[-1].rsplit(",", 1)[-1]
        if _NEGATION_RX.search(clause):
            continue                                  # "not everything is done" -> not a claim
        if _ADV_FORWARD_RX.search(clause):
            continue                                  # "once everything is done" -> forward promise
        return True                                   # a head quantifier binds this done-word
    return False


def _open_advance_claims(text, opens):
    return opens or () if _advance_signal(text) else ()


def _advance_discharged(claim, _c, *, touched_keys, fs_exists, empty_keys, fs_size) -> bool:
    return _discharged(
        claim["location"], touched_keys, fs_exists,
        empty_keys=empty_keys, fs_size=fs_size,
    ) or _adv_relocated_discharge(claim["location"], touched_keys)   # renamed path (FP fix)


def _advance_finding(claim, _c):
    loc_n = normalize_path(claim["location"])
    return Finding(
        pattern_id="gate.advance", file=loc_n, line=0, level="error",
        message=(f"Advancing past an open commitment to {loc_n} with no recorded result — "
                 "discharge it, or retract it with a checked reason."),
        retry_hint="Touch the location, or retract the commitment with a valid reason (R/U).",
    )


def advance_gate(text, open_commits, *, touched_keys, fs_exists=None, empty_keys=None,
                 fs_size=None) -> Optional[Finding]:
    """Fires when the AI claims UNIVERSAL completion while an open located commitment is
    undischarged — a verifiable contradiction between "everything is complete" and a promised
    path that is provably not done.

    Two conjuncts, both required (so it never fires on ordinary in-progress work or honest
    re-prioritization):
      1. `text` makes an unenumerated universal completion claim (see `_advance_signal`) — a
         bare "moving on" / scoped done / enumerated claim does NOT qualify, and
      2. an open commitment's location is undischarged (not in the ledger AND not on
         disk — fail-open re-derivation covers a dropped touch).
    Uncertain (no universal claim, no open commitments, empty text) -> None.

    This is the plain-argument twin of `run` below: both walk the same
    `_open_advance_claims`/`_advance_discharged`/`_advance_finding` triple, so the claim
    extraction, the discharge test and the message cannot drift between the GateContext wiring
    and this directly-callable form. The one thing it cannot supply is the GateContext itself —
    it passes None as the `_c` argument the two helpers currently ignore, so a helper that
    starts reading `_c` must grow a plain-argument path here too.
    """
    for claim in _open_advance_claims(text, open_commits):
        if _advance_discharged(claim, None, touched_keys=touched_keys, fs_exists=fs_exists,
                               empty_keys=empty_keys, fs_size=fs_size):
            continue
        return _advance_finding(claim, None)
    return None


run = claim_vs_ledger_predicate(
    extract_claims=_open_advance_claims,
    veto=_advance_discharged,
    message=_advance_finding,
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.advance", applies_at="Stop", posture="BLOCK", may_block=True,
               eats=DISCHARGE_EATS | frozenset({"text", "opens"}),
               run=run, tests="CLAIM_VS_LEDGER")
