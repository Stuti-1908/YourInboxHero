"""Tests for plan-tier feature entitlements — each feature's gate must match
exactly what the pricing page promises per plan."""
import pytest
from src.services.plan_features import plan_has_feature


@pytest.mark.parametrize("feature", ["voice_escalation", "custom_templates", "custom_branding", "custom_smtp"])
def test_starter_lacks_all_growth_plus_features(feature):
    assert plan_has_feature("starter", feature) is False


@pytest.mark.parametrize("feature", ["voice_escalation", "custom_templates", "custom_branding", "custom_smtp"])
def test_growth_has_all_growth_plus_features(feature):
    assert plan_has_feature("growth", feature) is True


@pytest.mark.parametrize("feature", ["voice_escalation", "custom_templates", "custom_branding", "custom_smtp"])
def test_scale_has_all_growth_plus_features(feature):
    """Plans are additive — Scale must include everything Growth has."""
    assert plan_has_feature("scale", feature) is True


def test_no_plan_at_all_has_no_features():
    """A None/empty subscription_plan (e.g. account never activated) must
    rank below even Starter, not accidentally pass a gate."""
    assert plan_has_feature(None, "voice_escalation") is False
    assert plan_has_feature("", "voice_escalation") is False


def test_plan_name_is_case_insensitive():
    assert plan_has_feature("GROWTH", "voice_escalation") is True
    assert plan_has_feature("Scale", "custom_templates") is True


def test_unknown_feature_raises():
    with pytest.raises(ValueError):
        plan_has_feature("scale", "not_a_real_feature")


def test_unrecognized_plan_name_has_no_features():
    """A typo'd or legacy plan name must fail closed, not open."""
    assert plan_has_feature("enterprise", "voice_escalation") is False
