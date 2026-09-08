"""Unit tests for the gating function."""

import pytest
from app.services.gating import route, GateDecision, GateResult


class TestRoute:
    def test_below_tau_low_is_original(self):
        result = route(0.10, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.TIER1_ORIGINAL
        assert result.confidence == 0.10

    def test_above_tau_high_is_plagiarised(self):
        result = route(0.90, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.TIER1_PLAGIARISED
        assert result.confidence == 0.90

    def test_between_thresholds_escalates(self):
        result = route(0.50, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.ESCALATE_TO_TIER2
        assert result.confidence == 0.50

    def test_exactly_at_tau_low_escalates(self):
        # c1 >= tau_low and c1 <= tau_high → escalate
        result = route(0.25, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.ESCALATE_TO_TIER2

    def test_exactly_at_tau_high_escalates(self):
        # c1 <= tau_high (not >) → escalate
        result = route(0.75, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.ESCALATE_TO_TIER2

    def test_zero_score(self):
        result = route(0.0, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.TIER1_ORIGINAL

    def test_perfect_score(self):
        result = route(1.0, tau_low=0.25, tau_high=0.75)
        assert result.decision == GateDecision.TIER1_PLAGIARISED

    def test_custom_thresholds(self):
        result = route(0.15, tau_low=0.10, tau_high=0.50)
        assert result.decision == GateDecision.ESCALATE_TO_TIER2

    def test_reason_includes_score(self):
        result = route(0.50, tau_low=0.25, tau_high=0.75)
        assert "0.500" in result.reason

    def test_returns_gate_result_type(self):
        result = route(0.5)
        assert isinstance(result, GateResult)
        assert isinstance(result.decision, GateDecision)
