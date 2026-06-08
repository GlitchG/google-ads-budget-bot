"""Contextual best-practice tips, triggered by what the analysis actually found.

Prefers the Markdown knowledge base (src/kb.py); falls back to the built-ins below.
Returns the 2-4 most relevant tips so the report stays actionable.
"""
from __future__ import annotations

from . import kb
from .ads import Campaign


def _context(serving: list[Campaign]) -> set[str]:
    ch = {c.channel for c in serving}
    ctx: set[str] = set()
    if "PERFORMANCE_MAX" in ch:
        ctx.add("pmax")
    if {"DEMAND_GEN", "DISPLAY", "VIDEO"} & ch:
        ctx.add("demandgen")
    if any(c.is_brand for c in serving):
        ctx.add("brand")
    if any(c.rank_lost_is >= 0.30 for c in serving if c.channel in ("SEARCH", "SHOPPING")):
        ctx.add("rank")
    return ctx


def generate_tips(serving: list[Campaign]) -> list[str]:
    # Prefer the Markdown knowledge base; fall back to the built-ins.
    kb_tips = kb.select_tips(_context(serving), k=4)
    if kb_tips:
        return kb_tips
    return _builtin_tips(serving)


def _builtin_tips(serving: list[Campaign]) -> list[str]:
    tips: list[str] = []
    channels = {c.channel for c in serving}
    has_pmax = "PERFORMANCE_MAX" in channels
    has_brand = any(c.is_brand for c in serving)
    has_search_or_shop = bool({"SEARCH", "SHOPPING"} & channels)

    dg = [c for c in serving if c.channel in ("DEMAND_GEN", "DISPLAY", "VIDEO") and c.cost > 0]
    if dg and any(c.roas < 1 for c in dg):
        tips.append("📺 Demand Gen/Display are upper-funnel: judge on view-through/assisted "
                    "conversions, not last-click ROAS. If still empty there, cap the budget.")

    if has_pmax and (has_brand or has_search_or_shop):
        tips.append("🛡️ PMax can cannibalise brand/search: add brand exclusions and your top "
                    "non-brand keywords as PMax campaign-level negatives so those queries route "
                    "to Search/Shopping.")

    if any(c.budget_limited for c in serving if not c.is_brand):
        tips.append("📈 Scale winners in ~15-20% steps every 3-5 days and keep a 10-15% buffer on "
                    "the tROAS target — a sharp budget jump resets Smart Bidding learning.")

    if any(c.rank_lost_is >= 0.30 for c in serving if c.channel in ("SEARCH", "SHOPPING")):
        tips.append("🎯 Impression share lost to rank is an Ad Rank problem, not budget: bids, "
                    "ad/asset quality, landing-page relevance.")

    if has_brand:
        tips.append("🏷️ Keep brand in its own campaign (Max Clicks/Manual CPC) for full coverage; "
                    "brand ROAS is inflated — don't use it as a scaling signal.")

    if not tips:
        tips.append("✅ Healthy structure. Watch IS lost to budget and reallocate weekly from weak "
                    "to strong campaigns.")
    return tips[:4]
