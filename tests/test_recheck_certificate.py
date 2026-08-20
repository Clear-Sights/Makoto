from __future__ import annotations

from pathlib import Path

import pytest

from makoto.vocab import Finding
from makoto import dispatch, verdict as posture
from makoto.verdict import VerdictCertificate, recheck_certificate


def _blocking_finding() -> Finding:
    return Finding(
        pattern_id="gate.completion",
        file="plan.md",
        line=7,
        level="error",
        message="A required plan item remains open.",
        retry_hint="Complete or retract the open item.",
    )


def test_real_findings_certificate_self_verifies():
    """The claimed detail is spelled out here, not produced by `_jit_hint`.

    Rebuilding the expectation with the helper under test would make this tautological -- the
    assertion would hold for whatever the helper emitted, including nothing. Only the conventions
    PATH is derived, from the package layout, because a literal absolute path is green in exactly
    one checkout: it was `/home/user/Makoto/...` and reddened the dev twin (and would have
    reddened every CI runner) while the two trees were byte-identical.
    """
    finding = _blocking_finding()
    conventions = Path(dispatch.__file__).resolve().parent / "docs" / "MAKOTO-CONVENTIONS.md"
    detail = ("A required plan item remains open.\n"
              "Complete or retract the open item.\n"
              f"Conventions: {conventions}")
    certificate = VerdictCertificate(
        findings=(finding,),
        mode=posture.STRICT,
        permission_mode=None,
        claimed_outcome=posture.BLOCK,
        claimed_detail=detail,
    )

    assert recheck_certificate(certificate) == (posture.BLOCK, detail)


def test_mutated_claim_is_rejected():
    certificate = VerdictCertificate(
        findings=(_blocking_finding(),),
        mode=posture.STRICT,
        permission_mode=None,
        claimed_outcome=posture.ALLOW,
        claimed_detail="",
    )

    with pytest.raises(ValueError, match="certificate claim does not match"):
        recheck_certificate(certificate)


@pytest.mark.parametrize(
    "claimed_outcome, claimed_detail",
    [(posture.BLOCK, "fabricated block"), (posture.ALLOW, "unexpected detail")],
)
def test_no_findings_certificate_rejects_forged_claims(claimed_outcome, claimed_detail):
    certificate = VerdictCertificate((), posture.STRICT, None, claimed_outcome, claimed_detail)
    with pytest.raises(ValueError, match="certificate claim does not match"):
        recheck_certificate(certificate)


def test_no_findings_certificate_self_verifies_under_permission_mode():
    certificate = VerdictCertificate((), posture.STRICT, "dontAsk", posture.ALLOW, "")
    assert recheck_certificate(certificate) == (posture.ALLOW, "")
