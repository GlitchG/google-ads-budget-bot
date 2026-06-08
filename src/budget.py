"""Budget write path (per account, gated behind Telegram approval). Budgets only.

Scale budget-limited profitable campaigns (ROAS >= scale floor); trim below
break-even. Brand & shared budgets never auto-changed. ±MAX_BUDGET_STEP.
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from .ads import Campaign, _client


@dataclass
class BudgetAction:
    cid: str
    campaign: str
    budget_id: int
    current_micros: int
    proposed_micros: int
    direction: str
    reason: str

    @property
    def token(self) -> str:
        return f"{self.cid}:{self.budget_id}"


def build_actions(cid: str, serving: list[Campaign], margin: float):
    """Returns (actions, skipped). `skipped` = campaigns the logic WANTED to act
    on but couldn't auto-change (brand / shared budget), so you handle them manually."""
    break_even = (1.0 / margin) if margin > 0 else 0.0
    scale_floor = break_even * (1 + config.SCALE_BUFFER)
    cut_floor = break_even
    step = config.MAX_BUDGET_STEP
    actions: list[BudgetAction] = []
    skipped: list[tuple[str, str]] = []
    for c in serving:
        want_up = c.budget_limited and c.roas >= scale_floor and c.conversions > 0
        want_down = c.cost > 0 and c.roas < cut_floor
        if not (want_up or want_down):
            continue
        verb = "raise" if want_up else "lower"
        if c.is_brand:
            skipped.append((c.name, f"brand — {verb} manually (not scaled on ROAS)"))
            continue
        if c.budget_shared:
            skipped.append((c.name, f"shared budget — {verb} manually (affects other campaigns)"))
            continue
        if c.daily_budget <= 0:
            continue
        cur = round(c.daily_budget)
        if want_up:
            new = round(c.daily_budget * (1 + step))
            if new > cur:
                actions.append(BudgetAction(cid, c.name, c.budget_id, int(cur * 1e6),
                    int(new * 1e6), "up",
                    f"profitable + capped, ROAS {c.roas:.1f} (floor {scale_floor:.1f}, break-even {cut_floor:.1f})"))
        else:
            new = round(c.daily_budget * (1 - step))
            if 0 < new < cur:
                actions.append(BudgetAction(cid, c.name, c.budget_id, int(cur * 1e6),
                    int(new * 1e6), "down",
                    f"unprofitable, ROAS {c.roas:.1f} &lt; break-even {cut_floor:.1f}"))
    return actions, skipped


def apply_budget(cid: str, budget_id: int, new_micros: int, validate_only: bool = False) -> None:
    from google.api_core import protobuf_helpers
    client = _client()
    svc = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    b = op.update
    b.resource_name = svc.campaign_budget_path(cid, budget_id)
    b.amount_micros = new_micros
    client.copy_from(op.update_mask, protobuf_helpers.field_mask(None, b._pb))
    req = client.get_type("MutateCampaignBudgetsRequest")
    req.customer_id = cid
    req.operations = [op]
    req.validate_only = validate_only
    svc.mutate_campaign_budgets(request=req)
