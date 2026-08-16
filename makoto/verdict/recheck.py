"""Certificates that recheck a claimed verdict against its raw fold inputs."""

from __future__ import annotations

from dataclasses import dataclass

from makoto.core.schema import Finding
from makoto.verdict.posture import ALLOW, BLOCK, Decision, apply


@dataclass(frozen=True)
class VerdictCertificate:
    """Raw verdict inputs paired with the outcome and detail they claim."""

    findings: tuple[Finding, ...]
    mode: str
    permission_mode: str | None
    claimed_outcome: str
    claimed_detail: str


def recheck_certificate(certificate: VerdictCertificate) -> tuple[str, str]:
    """Reconstruct and verify a certificate's claimed ``(outcome, detail)``.

    A mismatch raises deliberately instead of following ``_dispatch.py``'s per-check
    ``try/except: continue`` fail-open convention. A broken individual check must not suppress
    other checks, but a fold-aggregator mismatch invalidates the verdict itself and is therefore
    not a per-check fault that can safely be ignored.
    """
    # Local so the later F4 wiring can import this module from _dispatch without an import cycle.
    from makoto._dispatch import _jit_hint, _worst_finding

    worst = _worst_finding(list(certificate.findings))
    if worst is None:
        reconstructed = (ALLOW, "")
    else:
        outcome, finding = worst
        detail = finding.message
        if outcome == BLOCK:
            hint = _jit_hint(finding)
            if hint:
                detail = f"{detail}\n{hint}"
        folded = apply(
            Decision(outcome, detail),
            certificate.mode,
            permission_mode=certificate.permission_mode,
        )
        reconstructed = (str(folded), getattr(folded, "detail", ""))

    claimed = (certificate.claimed_outcome, certificate.claimed_detail)
    if reconstructed != claimed:
        raise ValueError(
            f"certificate claim does not match reconstruction: "
            f"claimed={claimed!r}, reconstructed={reconstructed!r}"
        )
    return reconstructed
