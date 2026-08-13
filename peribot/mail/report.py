from datetime import date, datetime

URGENCY_THRESHOLD = 4


def build_report(results: dict, run_time: datetime, cost_summary: dict = None) -> str:
    header = f"# 📬 PeriMail Report — {run_time.strftime('%Y-%m-%d %H:%M')} UTC"

    if not results:
        body = f"{header}\n\nNo accounts registered."
        return _append_cost(body, cost_summary)

    lines = [header, ""]
    total_rules = total_gemini = total_failed = 0
    total_proposals = 0
    all_urgent = []

    for email, result in results.items():
        lines.append(f"## {email}")
        if result.error:
            if "invalid_grant" in result.error:
                lines.append("> ⚠️ Google session expired — reconnect with /add-account (reauth)")
            else:
                lines.append(f"> ⚠️ Run failed: {result.error[:120]}")
            lines.append("")
            continue
        if not result.category_counts:
            lines.append("No new emails")
        else:
            for cat, count in sorted(result.category_counts.items()):
                lines.append(f"- **{cat}** — {count}")
        if result.gemini_picks:
            lines.append("")
            lines.append("**Gemini picks:**")
            for subject, category in result.gemini_picks:
                lines.append(f"- {subject[:50]} → **{category}**")
        lines.append("")
        total_rules += result.rules_count
        total_gemini += result.gemini_count
        total_failed += result.failed_count
        total_proposals += result.proposals_count
        all_urgent.extend(result.urgent)

    urgent = sorted((u for u in all_urgent if u[0] >= URGENCY_THRESHOLD), key=lambda x: x[0], reverse=True)
    if urgent:
        lines.append("## ⚠️ Needs attention")
        for score, subject in urgent:
            lines.append(f"- **[{score}]** {subject[:60]}")
        lines.append("")

    if total_proposals:
        lines.append(f"💡 Proposed {total_proposals} new categories — approve in Discord.")
        lines.append("")

    lines.append("---")
    lines.append(f"**Totals** — Rules: {total_rules} · Gemini: {total_gemini} · Failed: {total_failed}")
    return _append_cost("\n".join(lines), cost_summary)


def format_cost_footer(cost_summary: dict) -> str:
    """Returns the cost footer line, or '' if cost_summary is falsy."""
    if not cost_summary:
        return ""
    return (
        f"Est. Gemini cost ({cost_summary['month']}): "
        f"${cost_summary['cost']:.4f} — {cost_summary['calls']} calls, {cost_summary['tokens']} tokens"
    )


def _append_cost(body: str, cost_summary: dict) -> str:
    footer = format_cost_footer(cost_summary)
    if not footer:
        return body
    return f"{body}\n\n-# {footer}"


_MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def build_calendar_section(events_by_account: dict, target_date: date) -> str:
    date_str = f"{target_date.day} {_MONTH_NAMES[target_date.month - 1]}"
    lines = [f"## 📅 Calendar — Today, {date_str}", ""]

    for email, events in events_by_account.items():
        lines.append(f"**{email}**")
        if not events:
            lines.append("- No events")
        else:
            for event in events:
                if event.all_day:
                    lines.append(f"- All day — {event.title}")
                else:
                    lines.append(f"- `{event.start.strftime('%H:%M')}` — {event.title}")
        lines.append("")

    if not events_by_account:
        lines.append("No events today.")

    return "\n".join(lines)
