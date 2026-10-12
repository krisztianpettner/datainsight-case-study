# ARCH-DOC: docs/architecture/06-clearadmin-billing-integration.md#pricing-sot
"""S160 BR8 — single source of truth for the platform fee + graduated usage pricing.

Previously the €39 platform fee and the 4-tier per-fatura rates were duplicated, with
no enforcement, in THREE places (BR8):
  - api/routes/client_billing.py  (float, API display)
  - tasks/billing_aggregation.py  (Decimal, billing math)
  - kirendeltseg/frontend/src/config/pricing.js  (JS, frontend display)

This module is the canonical PYTHON source; both Python call-sites now import from here.
`pricing.js` stays the frontend mirror (separate runtime) — keep it in sync by hand.

Decimal is canonical (money math). `monthly_cost_float` exists only for the API display
response (BalanceResponse.estimated_cost_eur). Numbers mirror the legacy implementations
bit-for-bit (verified by a differential sweep test).
"""
from decimal import Decimal
from typing import List, Optional, Tuple

PLATFORM_FEE_EUR: Decimal = Decimal("39.00")

# (from_count, to_count_inclusive_or_None, eur_per_unit) — graduated tiers.
PRICING_TIERS: List[Tuple[int, Optional[int], Decimal]] = [
    (1, 60, Decimal("1.75")),
    (61, 120, Decimal("1.65")),
    (121, 300, Decimal("1.55")),
    (301, None, Decimal("1.45")),
]

_CENT = Decimal("0.01")


def usage_charge(billable_count: int) -> Decimal:
    """Progressive tier-based usage charge in EUR (EXCLUDES the platform fee).

    `billable_count` = faturas billable this period (after trial + bonus deduction).
    Bit-identical to the legacy tasks/billing_aggregation._calculate_usage_eur.
    """
    if billable_count <= 0:
        return Decimal("0.00")
    usage = Decimal("0.00")
    remaining = billable_count
    for from_n, to_n, per_unit in PRICING_TIERS:
        if remaining <= 0:
            break
        tier_width = (to_n - from_n + 1) if to_n is not None else remaining
        units_in_tier = min(remaining, tier_width)
        usage += Decimal(units_in_tier) * per_unit
        remaining -= units_in_tier
    return usage.quantize(_CENT)


def monthly_cost(billable_count: int) -> Decimal:
    """Platform fee + tiered usage. billable_count <= 0 → platform fee only."""
    return (PLATFORM_FEE_EUR + usage_charge(billable_count)).quantize(_CENT)


def monthly_cost_float(billable_count: int) -> float:
    """Float view for the API display (BalanceResponse.estimated_cost_eur)."""
    return float(monthly_cost(billable_count))
