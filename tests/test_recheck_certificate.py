from __future__ import annotations

import pytest

from makoto._dispatch import _jit_hint
from makoto.core.schema import Finding
from makoto.verdict import posture
from makoto.verdict.recheck import VerdictCertificate, recheck_certificate


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
    finding = _blocking_finding()
    detail = f"{finding.message}\n{_jit_hint(finding)}"
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
