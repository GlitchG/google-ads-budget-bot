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
