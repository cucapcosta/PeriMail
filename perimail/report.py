from datetime import date, datetime


def build_report(results: dict, run_time: datetime) -> str:
    header = f"**PeriMail Report — {run_time.strftime('%Y-%m-%d %H:%M')} UTC**"

    if not results:
        return f"{header}\n\nNo accounts registered."

    lines = [header, ""]
    total_rules = total_gemini = total_failed = 0

    for email, result in results.items():
        lines.append(f"**{email}**")
        if not result.category_counts:
            lines.append("  No new emails")
        else:
            for cat, count in sorted(result.category_counts.items()):
                lines.append(f"  {cat:<22} {count}")
        lines.append("")
        total_rules += result.rules_count
        total_gemini += result.gemini_count
        total_failed += result.failed_count

    lines.append(
        f"Classified by rules: {total_rules} | Gemini: {total_gemini} | Failed: {total_failed}"
    )
    return "\n".join(lines)


_MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def build_calendar_section(events_by_account: dict, target_date: date) -> str:
    date_str = f"{target_date.day} {_MONTH_NAMES[target_date.month - 1]}"
    lines = [f"**Calendar — Today, {date_str}**", ""]

    for email, events in events_by_account.items():
        lines.append(f"**{email}**")
        if not events:
            lines.append("  No events")
        else:
            for event in events:
                if event.all_day:
                    lines.append(f"  All day  {event.title}")
                else:
                    lines.append(f"  {event.start.strftime('%H:%M')}  {event.title}")
        lines.append("")

    if not events_by_account:
        lines.append("No events today.")

    return "\n".join(lines)
