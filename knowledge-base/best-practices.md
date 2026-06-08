# Google Ads Optimization — Best Practices KB

The bot reads the bullets below and surfaces the ones relevant to each account in
its weekly report. Add new practices here (manually, or via a scheduled agent) and
they show up automatically — no code change needed. Keep entries concise and
actionable. Bullets under "Sources"/"Changelog" are ignored.

## Budgets & scaling
- **Profitability, not average ROAS, is the scaling signal.** break-even ROAS = 1 / gross-margin. Scale any budget-limited campaign whose ROAS is above break-even (plus a cushion) — even if below account average. The goal is max profit, not max ROAS.
- **Scale in steps of ~15-20% every 3-5 days.** Large jumps reset Smart Bidding learning. Keep a 10-15% buffer on tROAS/tCPA targets while scaling.
- **`campaign.primary_status = LIMITED` is the authoritative "budget-constrained" signal** — trust it over home-grown pacing math, especially for Performance Max (which does not report budget lost IS).
- **Cut only below break-even.** A campaign between break-even and account average is still profitable — do not starve it.

## Conversion data hygiene
- **Account for conversion lag.** If value lands days after the click, end the analysis window N days before today so decisions use settled data; otherwise recent ROAS is understated and you cut winners.
- **Verify ROAS is built from real revenue** (a single purchase action), not inflated by micro-conversions (form opens, add-to-cart) counted with value.
- **Use `campaign.primary_status` (ELIGIBLE/LIMITED), not `campaign.status`,** to find truly-serving campaigns — `status` stays ENABLED on ENDED campaigns.

## Channel-specific
- **Brand search:** never scale on ROAS (inflated — it harvests existing demand). Keep it on its own campaign for full coverage; exclude brand from Performance Max via brand exclusions.
- **Performance Max cannibalisation:** add brand exclusions plus top non-brand keywords as campaign-level negatives so those queries route to Search/Shopping.
- **Demand Gen / Display / Video** are upper-funnel — judge on view-through/assisted conversions, not last-click ROAS. If still unprofitable there, cap budget.
- **Impression share lost to rank** (Search/Shopping) is a bid/quality/Ad-Rank problem, not budget — raising budget will not fix it.

## Account structure
- A common starting split: ~40-50% Search, ~25-40% Performance Max, remainder Demand Gen/other — adjust to catalog and business model.
- Reallocate weekly: move budget from below-break-even campaigns to profitable budget-limited ones.

## Sources
- Industry best-practice guides (2026). Add your own sources here.

## Changelog
- Initial seed.
