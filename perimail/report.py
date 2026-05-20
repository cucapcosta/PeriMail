from datetime import datetime


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
