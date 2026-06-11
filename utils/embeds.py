import discord
from datetime import datetime, timezone

# Vendors need at least this many ratings before they are tier-classified.
MIN_RATINGS_FOR_TIER = 3


def tier_info(score: float) -> tuple[str, str]:
    if score >= 8:
        return ("🟢", "APPROVED")
    elif score >= 4:
        return ("🟡", "USE WITH CAUTION")
    else:
        return ("🔴", "DO NOT USE")


def build_vendor_list_embed(vendor_stats: list) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Vendor Ratings",
        description=(
            "Anonymous ratings submitted by community members.\n"
            "Use `/rate` to submit a rating · `/suggest` to add a vendor."
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )

    if not vendor_stats:
        embed.add_field(
            name="No vendors yet",
            value="Suggest one with `/suggest <name>`",
            inline=False,
        )
        embed.set_footer(text="Last updated")
        return embed

    buckets: dict[str, list] = {
        "approved": [],
        "caution": [],
        "do_not_use": [],
        "gathering": [],
        "unrated": [],
    }

    for row in vendor_stats:
        name = row["name"]
        avg = float(row["avg_score"])
        count = int(row["rating_count"])

        if count == 0:
            buckets["unrated"].append((name, avg, count))
        elif count < MIN_RATINGS_FOR_TIER:
            buckets["gathering"].append((name, avg, count))
        elif avg >= 8:
            buckets["approved"].append((name, avg, count))
        elif avg >= 4:
            buckets["caution"].append((name, avg, count))
        else:
            buckets["do_not_use"].append((name, avg, count))

    def fmt_rows(rows: list) -> str:
        lines = []
        for name, avg, count in sorted(rows, key=lambda x: -x[1]):
            score_str = f"**{avg:.1f}**/10"
            count_str = f"{count} rating{'s' if count != 1 else ''}"
            lines.append(f"**{name}** — {score_str} ({count_str})")
        return "\n".join(lines)

    sections = [
        ("🟢 APPROVED  ·  8–10", buckets["approved"]),
        ("🟡 USE WITH CAUTION  ·  4–7", buckets["caution"]),
        ("🔴 DO NOT USE  ·  1–3", buckets["do_not_use"]),
    ]

    for title, rows in sections:
        if rows:
            embed.add_field(name=title, value=fmt_rows(rows), inline=False)

    if buckets["gathering"]:
        # No average shown on purpose — these vendors aren't classified yet.
        value = "\n".join(
            f"**{name}** — {count}/{MIN_RATINGS_FOR_TIER} ratings"
            for name, _, count in sorted(
                buckets["gathering"], key=lambda x: (-x[2], x[0].lower())
            )
        )
        embed.add_field(
            name=f"🔵 GATHERING REVIEWS  ·  rated after {MIN_RATINGS_FOR_TIER}+",
            value=value,
            inline=False,
        )

    if buckets["unrated"]:
        value = "\n".join(f"**{name}**" for name, _, _ in buckets["unrated"])
        embed.add_field(name="⚪ NOT YET RATED", value=value, inline=False)

    total = sum(int(r["rating_count"]) for r in vendor_stats)
    embed.set_footer(text=f"Last updated  ·  {total} total rating{'s' if total != 1 else ''}")
    return embed


def build_suggestion_embed(vendor_name: str, suggested_by: discord.Member, vendor_id: int) -> discord.Embed:
    embed = discord.Embed(
        title="🆕 New Vendor Suggestion",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Vendor", value=vendor_name, inline=True)
    embed.add_field(name="Suggested by", value=suggested_by.mention, inline=True)
    embed.add_field(name="Vendor ID", value=str(vendor_id), inline=True)
    embed.set_footer(text="Use the buttons below or /approve / /reject")
    return embed
