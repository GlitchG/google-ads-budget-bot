"""Google Ads read layer — multi-account. Every call takes a customer id (cid)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import config

CAMPAIGN_GAQL = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.primary_status,
  campaign.advertising_channel_type,
  campaign.bidding_strategy_type,
  campaign_budget.id,
  campaign_budget.amount_micros,
  campaign_budget.explicitly_shared,
  campaign_budget.reference_count,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value,
  metrics.clicks,
  metrics.impressions,
  metrics.search_budget_lost_impression_share,
  metrics.search_rank_lost_impression_share,
  metrics.search_impression_share
FROM campaign
WHERE segments.date BETWEEN '{start}' AND '{end}'
"""

SERVING_STATUSES = {"ELIGIBLE", "LIMITED"}
# Name tokens that mark a brand campaign. Add your own (e.g. localized words).
BRAND_TOKENS = ("brand",)


@dataclass
class Campaign:
    id: int
    name: str
    channel: str
    bidding: str
    primary_status: str
    budget_id: int
    daily_budget: float
    budget_shared: bool
    cost: float
    conversions: float
    conv_value: float
    clicks: int
    impressions: int
    budget_lost_is: float
    rank_lost_is: float
    search_is: float

    @property
    def roas(self) -> float:
        return self.conv_value / self.cost if self.cost else 0.0

    @property
    def serving(self) -> bool:
        return self.primary_status in SERVING_STATUSES

    @property
    def is_brand(self) -> bool:
        n = self.name.lower()
        return any(t in n for t in BRAND_TOKENS)

    @property
    def budget_limited(self) -> bool:
        return self.primary_status == "LIMITED" or self.budget_lost_is >= 0.10


def _client():
    from google.ads.googleads.client import GoogleAdsClient
    return GoogleAdsClient.load_from_dict(config.google_ads_config())


def account_today(tz: str) -> dt.date:
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(tz)).date()


def account_name(cid: str) -> str:
    ga = _client().get_service("GoogleAdsService")
    for b in ga.search_stream(customer_id=cid,
                              query="SELECT customer.descriptive_name FROM customer"):
        for r in b.results:
            return r.customer.descriptive_name
    return cid


def pull_campaigns(cid: str, start: dt.date, end: dt.date) -> list[Campaign]:
    ga = _client().get_service("GoogleAdsService")
    q = CAMPAIGN_GAQL.format(start=f"{start:%Y-%m-%d}", end=f"{end:%Y-%m-%d}")
    out: list[Campaign] = []
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            m = r.metrics
            out.append(Campaign(
                id=r.campaign.id,
                name=r.campaign.name,
                channel=r.campaign.advertising_channel_type.name,
                bidding=r.campaign.bidding_strategy_type.name,
                primary_status=r.campaign.primary_status.name,
                budget_id=r.campaign_budget.id,
                daily_budget=r.campaign_budget.amount_micros / 1e6,
                budget_shared=(r.campaign_budget.explicitly_shared
                               or r.campaign_budget.reference_count > 1),
                cost=m.cost_micros / 1e6,
                conversions=m.conversions,
                conv_value=m.conversions_value,
                clicks=m.clicks,
                impressions=m.impressions,
                budget_lost_is=m.search_budget_lost_impression_share or 0.0,
                rank_lost_is=m.search_rank_lost_impression_share or 0.0,
                search_is=m.search_impression_share or 0.0,
            ))
    return out


def pull_two_periods(cid: str, tz: str, days: int = 7, lag: int | None = None):
    if lag is None:
        lag = config.CONVERSION_LAG_DAYS
    end = account_today(tz) - dt.timedelta(days=lag)
    cur_start = end - dt.timedelta(days=days)
    prev_end = cur_start
    prev_start = prev_end - dt.timedelta(days=days)
    cur = pull_campaigns(cid, cur_start, end)
    prev = pull_campaigns(cid, prev_start, prev_end)
    return cur, prev, (cur_start, end), (prev_start, prev_end)


def account_totals(cid: str, start: dt.date, end: dt.date) -> tuple[float, float]:
    """Account-level (cost, conversions_value) for a date range — cheap, one row."""
    ga = _client().get_service("GoogleAdsService")
    q = (f"SELECT metrics.cost_micros, metrics.conversions_value FROM customer "
         f"WHERE segments.date BETWEEN '{start:%Y-%m-%d}' AND '{end:%Y-%m-%d}'")
    cost = val = 0.0
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            cost += r.metrics.cost_micros / 1e6
            val += r.metrics.conversions_value
    return cost, val


def campaign_deltas(cur: list[Campaign], prev: list[Campaign]) -> dict[str, dict]:
    """Per-campaign {name: {cost, roas, d_cost, d_roas, is_new}} for already-pulled
    periods (e.g. the weekly cur/prev). Spending campaigns only."""
    prev_by = {c.id: c for c in prev}

    def d(now: float, was: float) -> float:
        return (now - was) / was if was else 0.0

    out: dict[str, dict] = {}
    for c in cur:
        if c.cost <= 0:
            continue
        p = prev_by.get(c.id)
        p_cost = p.cost if p else 0.0
        out[c.name] = {
            "cost": c.cost, "roas": c.roas,
            "d_cost": d(c.cost, p_cost),
            "d_roas": d(c.roas, p.roas if p else 0.0),
            "is_new": p is None or p_cost == 0,
        }
    return out


def campaign_monthly(cid: str, tz: str, days: int = 30, lag: int | None = None) -> list[dict]:
    """Per-campaign performance for the last `days` vs the prior `days`
    (conversion-lag adjusted). Spending campaigns only, sorted by spend desc."""
    if lag is None:
        lag = config.CONVERSION_LAG_DAYS
    end = account_today(tz) - dt.timedelta(days=lag)
    cur_start = end - dt.timedelta(days=days)
    prev_start = cur_start - dt.timedelta(days=days)
    cur = pull_campaigns(cid, cur_start, end)
    prev_by = {c.id: c for c in pull_campaigns(cid, prev_start, cur_start)}

    def d(now: float, was: float) -> float:
        return (now - was) / was if was else 0.0

    rows = []
    for c in cur:
        if c.cost <= 0:
            continue
        p = prev_by.get(c.id)
        p_cost = p.cost if p else 0.0
        p_roas = p.roas if p else 0.0
        rows.append({
            "name": c.name, "cost": c.cost, "roas": c.roas,
            "d_cost": d(c.cost, p_cost), "d_roas": d(c.roas, p_roas),
            "is_new": p is None or p_cost == 0,
        })
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return rows


def monthly_trend(cid: str, tz: str, margin: float, days: int = 30,
                  lag: int | None = None) -> dict:
    """Last `days` vs the prior `days` (conversion-lag adjusted) at account level."""
    if lag is None:
        lag = config.CONVERSION_LAG_DAYS
    end = account_today(tz) - dt.timedelta(days=lag)
    cur_start = end - dt.timedelta(days=days)
    prev_start = cur_start - dt.timedelta(days=days)
    c_cost, c_val = account_totals(cid, cur_start, end)
    p_cost, p_val = account_totals(cid, prev_start, cur_start)
    profit = c_val * margin - c_cost
    prev_profit = p_val * margin - p_cost

    def d(now: float, was: float) -> float:
        return (now - was) / was if was else 0.0

    return {
        "days": days, "margin": margin,
        "cost": c_cost, "value": c_val, "profit": profit,
        "roas": (c_val / c_cost if c_cost else 0.0),
        "d_cost": d(c_cost, p_cost), "d_value": d(c_val, p_val),
        "d_profit": d(profit, prev_profit),
        "d_roas": d((c_val / c_cost if c_cost else 0.0), (p_val / p_cost if p_cost else 0.0)),
    }
