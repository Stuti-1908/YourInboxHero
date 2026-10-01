"""Plan-tier feature entitlements — what each plan promises on the pricing
page, enforced here rather than left as marketing copy with no teeth.

Plans are additive: Growth includes everything Starter has, Scale includes
everything Growth has. Only features actually enforceable in code are
listed here — "Priority support", "Dedicated account manager", and
"Custom SLAs" are support/ops commitments, not product gates, so they're
deliberately absent.
"""
from typing import Optional

PLAN_TIERS = {"starter": 0, "growth": 1, "scale": 2}

# The tier (by name) each feature first becomes available at.
FEATURE_MIN_TIER = {
    "voice_escalation": "growth",
    "custom_templates": "growth",
    "custom_branding": "growth",   # logo on invoices
    "custom_smtp": "growth",       # sending from your own domain
}


def _tier_rank(plan: Optional[str]) -> int:
    if not plan:
        return -1  # no plan at all ranks below every tier, including Starter
    return PLAN_TIERS.get(plan.lower(), -1)


def plan_has_feature(plan: Optional[str], feature: str) -> bool:
    """True if `plan` includes `feature`, per the tier it first unlocks at."""
    min_tier = FEATURE_MIN_TIER.get(feature)
    if min_tier is None:
        raise ValueError(f"Unknown feature: {feature}")
    return _tier_rank(plan) >= _tier_rank(min_tier)
