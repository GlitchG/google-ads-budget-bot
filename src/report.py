"""Format the weekly analysis into a Telegram (HTML) report."""
from __future__ import annotations

import config
from .analysis import Finding

SEV_ICON = {"high": "🔴", "med": "🟡", "low": "⚪"}


def _money(x: float) -> str:
    return f"{config.CURRENCY}{x:,.0f}"


def _dyn(d: float) -> str:
    if abs(d) < 0.005:
        return "→ 0%"
    return f"{'▲' if d > 0 else '▼'}{abs(d) * 100:.0f}%"


def summary_block(result: dict) -> list[str]:
    s = result.get("summary", {})
    if not s:
        return []
    return [
        "<b>📈 Week summary (vs last week):</b>",
        f"• Spend: <b>{_money(s['cost'])}</b>  {_dyn(s['d_cost'])}",
        f"• Revenue: <b>{_money(s['value'])}</b>  {_dyn(s['d_value'])}",
        f"• Profit (revenue×{s['margin']*100:.0f}% − ads): <b>{_money(s['profit'])}</b>  {_dyn(s['d_profit'])}",
        f"• ROAS: <b>{s['roas']:.1f}</b>  {_dyn(s['d_roas'])}",
        "",
    ]


def monthly_block(result: dict) -> list[str]:
    m = result.get("monthly")
    if not m:
        return []
    return [
        f"<b>📅 Last {m['days']}d (vs prior {m['days']}d):</b>",
        f"• Spend: <b>{_money(m['cost'])}</b>  {_dyn(m['d_cost'])}",
        f"• Revenue: <b>{_money(m['value'])}</b>  {_dyn(m['d_value'])}",
        f"• Profit: <b>{_money(m['profit'])}</b>  {_dyn(m['d_profit'])}",
        f"• ROAS: <b>{m['roas']:.1f}</b>  {_dyn(m['d_roas'])}",
        "",
    ]


def campaign_monthly_block(result: dict, top: int = 8) -> list[str]:
    rows = result.get("campaign_monthly")
    if not rows:
        return []
    out = ["<b>📅 Campaigns, last 30d (spend · ROAS · Δ ROAS):</b>"]
    for r in rows[:top]:
        tag = " <i>(new)</i>" if r["is_new"] else f"  {_dyn(r['d_roas'])}"
        out.append(f"• <b>{r['name']}</b> — {_money(r['cost'])} · ROAS {r['roas']:.1f}{tag}")
    if len(rows) > top:
        out.append(f"  …and {len(rows) - top} more")
    out.append("")
    return out


def format_report(account: str, period: str, result: dict) -> str:
    f: list[Finding] = result["findings"]
    lines = [
        f"<b>📊 {account} — weekly audit</b>",
        f"<i>{period} (conversion lag applied)</i>",
        "",
        *summary_block(result),
        *monthly_block(result),
        f"Break-even ROAS <b>{result.get('break_even', 0):.1f}</b> · "
        f"scale floor <b>{result.get('scale_floor', 0):.1f}</b> · "
        f"{result['n_spending']}/{result['n_campaigns']} serving",
        "",
    ]
    if not f:
        lines.append("✅ No material issues this period.")
        lines.append("")
        lines += campaign_monthly_block(result)
        return "\n".join(lines)

    highs = sum(1 for x in f if x.severity == "high")
    lines.append(f"<b>Findings ({len(f)}):</b> 🔴{highs} priority")
    lines.append("")
    for x in f:
        lines.append(f"{SEV_ICON.get(x.severity, '•')} <b>[{x.area}]</b> {x.text}")
        lines.append("")
    lines += campaign_monthly_block(result)
    return "\n".join(lines)
