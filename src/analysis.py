"""Per-account, margin-aware weekly analysis. Read-only — produces findings only.

Goal: maximize profit at the account's margin.
  break-even ROAS = 1/margin; scale floor = break-even * (1 + SCALE_BUFFER).
  Scale budget-limited campaigns with ROAS >= scale floor; cut below break-even.

Correctness rules:
  - serving-only (campaign.primary_status ELIGIBLE/LIMITED), not status
  - LIMITED is the authoritative budget-constrained signal
  - brand campaigns are never scaled on their inflated ROAS
  - rank-lost-IS advice only for Search/Shopping (PMax has no manual bids)
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from .ads import Campaign

SEV_ORDER = {"high": 0, "med": 1, "low": 2}


@dataclass
class Finding:
    severity: str
    area: str
    text: str


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _money(x: float) -> str:
    return f"{config.CURRENCY}{x:,.0f}"


def analyze(cur: list[Campaign], prev: list[Campaign], margin: float, days: int = 7) -> dict:
    break_even = (1.0 / margin) if margin > 0 else 0.0
    scale_floor = break_even * (1 + config.SCALE_BUFFER)
    cut_floor = break_even

    findings: list[Finding] = []
    serving = [c for c in cur if c.serving]
    nonbrand = [c for c in serving if not c.is_brand]
    spending = [c for c in serving if c.cost > 0]
    prev_by_id = {c.id: c for c in prev}

    total_cost = sum(c.cost for c in serving)
    total_val = sum(c.conv_value for c in serving)
    avg_roas = total_val / total_cost if total_cost else 0.0

    # Weekly summary + week-over-week dynamics (profit = revenue×margin − ad spend).
    prev_cost = sum(c.cost for c in prev)
    prev_val = sum(c.conv_value for c in prev)
    profit = total_val * margin - total_cost
    prev_profit = prev_val * margin - prev_cost
    prev_roas = prev_val / prev_cost if prev_cost else 0.0

    def _delta(now: float, was: float) -> float:
        return (now - was) / was if was else 0.0

    summary = {
        "margin": margin, "cost": total_cost, "value": total_val,
        "profit": profit, "roas": avg_roas,
        "d_cost": _delta(total_cost, prev_cost), "d_value": _delta(total_val, prev_val),
        "d_profit": _delta(profit, prev_profit), "d_roas": _delta(avg_roas, prev_roas),
    }

    # 1. Budget-limited campaigns
    for c in nonbrand:
        if not (c.budget_limited and c.cost > 0):
            continue
        why = ("Google: LIMITED" if c.primary_status == "LIMITED"
               else f"losing {_pct(c.budget_lost_is)} IS to budget")
        if c.roas >= scale_floor and c.conversions > 0:
            findings.append(Finding("high", "Scale: budget-capped",
                f"<b>{c.name}</b> — {why}, ROAS {c.roas:.1f} ≥ floor {scale_floor:.1f} "
                f"(break-even {cut_floor:.1f}). Raise budget +{config.MAX_BUDGET_STEP*100:.0f}% to grow revenue."))
        elif c.roas >= cut_floor:
            findings.append(Finding("med", "Scale: thin margin",
                f"<b>{c.name}</b> — {why}, ROAS {c.roas:.1f} (profitable but below floor "
                f"{scale_floor:.1f}). Scale cautiously or hold."))
        else:
            findings.append(Finding("med", "Loss + capped",
                f"<b>{c.name}</b> — {why}, ROAS {c.roas:.1f} &lt; break-even {cut_floor:.1f}. "
                f"Don't scale — improve efficiency or cut."))

    # 2. Cut / reallocate below break-even
    weak = [c for c in nonbrand if c.cost > 0 and c.roas < cut_floor]
    strong_limited = [c for c in nonbrand if c.budget_limited and c.roas >= scale_floor and c.cost > 0]
    if weak and strong_limited:
        donor = max(weak, key=lambda c: c.cost)
        recv = max(strong_limited, key=lambda c: c.roas)
        findings.append(Finding("high", "Reallocate",
            f"Move budget: <b>{donor.name}</b> (ROAS {donor.roas:.1f}, unprofitable, "
            f"{_money(donor.cost)}) → <b>{recv.name}</b> (ROAS {recv.roas:.1f}, profitable + capped)."))
    for c in weak:
        findings.append(Finding("high", "Unprofitable",
            f"<b>{c.name}</b> — ROAS {c.roas:.1f} &lt; break-even {cut_floor:.1f}, spends "
            f"{_money(c.cost)}. Eating profit — cut budget / review."))

    # 3. Anomalies: serving + budgeted but no spend; week-over-week swings
    for c in serving:
        if c.daily_budget > 0 and c.cost < 1:
            findings.append(Finding("high", "Zero-spend (active)",
                f"<b>{c.name}</b> — {c.primary_status}, budget {_money(c.daily_budget)}/day, "
                f"≈0 spend. Check bids / disapprovals / audience."))
    for c in spending:
        p = prev_by_id.get(c.id)
        if not p or p.cost < 1:
            continue
        dcost = (c.cost - p.cost) / p.cost
        if abs(dcost) >= config.WOW_DELTA:
            dconv = ((c.conversions - p.conversions) / p.conversions if p.conversions else 0.0)
            sev = "high" if dconv <= -0.5 else "med"
            findings.append(Finding(sev, "WoW anomaly",
                f"<b>{c.name}</b> — spend {'▲' if dcost > 0 else '▼'}{_pct(abs(dcost))} "
                f"({_money(p.cost)}→{_money(c.cost)}), conv {'▲' if dconv >= 0 else '▼'}{_pct(abs(dconv))}."))

    # 4. Rank-lost-IS (Search/Shopping only)
    for c in serving:
        if c.channel in ("SEARCH", "SHOPPING") and c.rank_lost_is >= 0.30 and c.cost > 0:
            findings.append(Finding("med", "Lost IS: rank",
                f"<b>{c.name}</b> — losing {_pct(c.rank_lost_is)} IS to rank (bid/quality, not budget)."))

    # 5. Clicks but no conversions
    for c in serving:
        if c.clicks >= config.NO_CONV_CLICKS and c.conversions == 0:
            findings.append(Finding("high", "Tracking/perf",
                f"<b>{c.name}</b> — {c.clicks} clicks, 0 conversions. Check conversion tracking / quality."))

    # 6. Brand coverage
    for c in serving:
        if c.is_brand and c.budget_limited and c.cost > 0:
            findings.append(Finding("med", "Brand coverage",
                f"<b>{c.name}</b> — brand is budget-limited. Brand isn't scaled on ROAS; "
                f"raise modestly for full coverage and add brand exclusions in PMax."))

    findings.sort(key=lambda f: SEV_ORDER.get(f.severity, 9))
    return {
        "total_cost": total_cost, "total_value": total_val, "avg_roas": avg_roas,
        "break_even": break_even, "scale_floor": scale_floor,
        "n_campaigns": len(serving), "n_spending": len(spending),
        "findings": findings, "serving": serving, "summary": summary,
    }
