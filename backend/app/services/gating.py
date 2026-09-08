"""Confidence gating function for dual-tier routing.

Routes submissions based on Tier 1 confidence score:
  c1 < τ_low  → ORIGINAL (stop)
  c1 > τ_high → PLAGIARISED (stop)
  else        → ESCALATE to Tier 2
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GateDecision(str, Enum):
    TIER1_ORIGINAL = "tier1_original"
    TIER1_PLAGIARISED = "tier1_plagiarised"
    ESCALATE_TO_TIER2 = "escalate_to_tier2"


@dataclass
class GateResult:
    decision: GateDecision
    confidence: float
    reason: str


def route(c1: float, tau_low: float = 0.25, tau_high: float = 0.75) -> GateResult:
    """Apply the gating function to a Tier 1 confidence score.

    Args:
        c1: Tier 1 confidence score, normalized to [0, 1].
        tau_low: Lower threshold. Below this → original.
        tau_high: Upper threshold. Above this → plagiarised.

    Returns:
        GateResult with decision, confidence, and reason.
    """
    if c1 < tau_low:
        return GateResult(
            decision=GateDecision.TIER1_ORIGINAL,
            confidence=c1,
            reason=f"Tier 1 score {c1:.3f} < τ_low {tau_low:.3f}",
        )
    elif c1 > tau_high:
        return GateResult(
            decision=GateDecision.TIER1_PLAGIARISED,
            confidence=c1,
            reason=f"Tier 1 score {c1:.3f} > τ_high {tau_high:.3f}",
        )
    else:
        return GateResult(
            decision=GateDecision.ESCALATE_TO_TIER2,
            confidence=c1,
            reason=f"Tier 1 score {c1:.3f} in ambiguous range [{tau_low:.3f}, {tau_high:.3f}]",
        )
