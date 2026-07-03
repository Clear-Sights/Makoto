from __future__ import annotations
import re
from typing import Optional
from makoto.checks import normalize_path
from makoto.schema import Finding
from makoto.lexicons import (
    _NEGATION_RX, _UNIVERSAL_DONE_RX, _SENTENCE_SPLIT_RX, _ADV_FORWARD_RX, _ENUM_BEFORE_HEAD_RX,
)
from makoto.lib.claims import _code_spans
from makoto.stopchecks._common import _discharged, _path_components
from makoto.stopchecks._types import StopCheck


# A version/variant rename suffix on a basename stem: parser_v2, config_old, handler-final, foo_copy.
_ADV_RENAME_SUFFIX_RX = re.compile(r"(?:[_-](?:v?\d+|new|old|final|copy|orig|backup|bak|tmp|temp))+$", re.I)


def _adv_stem_core(basename: str):
    """(stem, core): the basename minus extension, and that stem minus a trailing rename suffix."""
    stem = basename[:basename.rfind(".")] if "." in basename else basename
    return stem, _ADV_RENAME_SUFFIX_RX.sub("", stem)


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
    c_base = c_comps[-1]
    c_ext = c_base[c_base.rfind("."):] if "." in c_base else ""
    c_stem, c_core = _adv_stem_core(c_base)
    c_dir = c_comps[:-1]
    for k in touched_keys or ():
        k_comps = _path_components(k)
        if not k_comps:
            continue
        k_base = k_comps[-1]
        k_ext = k_base[k_base.rfind("."):] if "." in k_base else ""
        if k_ext.lower() != c_ext.lower():
            continue                                  # different file type -> not a rename
        same_dir = (bool(c_dir) and bool(k_comps[:-1]) and c_dir[-1] == k_comps[:-1][-1]) \
            or (not c_dir and not k_comps[:-1])
        if not same_dir:
            continue                                  # moved out of dir -> not a same-dir rename
        k_stem, k_core = _adv_stem_core(k_base)
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
def advance_gate(text, open_commits, *, touched_keys, fs_exists=None, empty_keys=None, fs_size=None) -> Optional[Finding]:
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
    """
    if not _advance_signal(text):
        return None
    for c in open_commits or ():
        if _discharged(c["location"], touched_keys, fs_exists, empty_keys=empty_keys, fs_size=fs_size):
            continue
        if _adv_relocated_discharge(c["location"], touched_keys):
            continue                                  # commitment satisfied at a renamed path (FP fix)
        loc_n = normalize_path(c["location"])
        return Finding(
            pattern_id="gate.advance",
            file=loc_n,
            line=0,
            level="error",
            message=(f"Advancing past an open commitment to {loc_n} with no recorded "
                     f"result — discharge it, or retract it with a checked reason."),
            retry_hint="Touch the location, or retract the commitment with a valid reason (R/U).",
        )
    return None


GATE = StopCheck(
    id="gate.advance",
    fn=advance_gate,
    run=lambda c: advance_gate(c.text, c.opens, touched_keys=c.touched, fs_exists=c.fs_exists, empty_keys=c.empty, fs_size=c.fs_size),
)
