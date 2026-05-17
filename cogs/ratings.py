import discord
from discord import app_commands
from discord.ext import commands


class RatingModal(discord.ui.Modal, title="Rate a Vendor"):
    score_input = discord.ui.TextInput(
        label="Score (1–10)",
        placeholder="Enter a whole number from 1 to 10",
        min_length=1,
        max_length=2,
        required=True,
    )
    comment_input = discord.ui.TextInput(
        label="Comment (optional)",
        placeholder="Share your experience — this is anonymous...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, vendor_id: int, vendor_name: str):
        super().__init__()
        self.vendor_id = vendor_id
        self.vendor_name = vendor_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            score = int(self.score_input.value.strip())
            if not 1 <= score <= 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Score must be a whole number between 1 and 10.", ephemeral=True
            )
            return

        comment = self.comment_input.value.strip() or None
        db = interaction.client.db

        cooldown_days = int(await db.get_config(interaction.guild_id, "cooldown_days") or 1)

        if await db.on_cooldown(interaction.user.id, self.vendor_id, cooldown_days):
            hours = await db.cooldown_hours_remaining(
                interaction.user.id, self.vendor_id, cooldown_days
            )
            await interaction.response.send_message(
                f"You already rated **{self.vendor_name}** recently.\n"
                f"You can submit another rating in **{hours}h** "
                f"(one per purchase, {cooldown_days}-day cooldown).",
                ephemeral=True,
            )
            return

        await db.add_rating(
            self.vendor_id,
            interaction.user.id,
            interaction.guild_id,
            score,
            comment,
            cooldown_days,
        )

        if score >= 8:
            tier = "🟢 APPROVED"
        elif score >= 4:
            tier = "🟡 USE WITH CAUTION"
        else:
            tier = "🔴 DO NOT USE"

        await interaction.response.send_message(
            f"{tier}\nYour anonymous rating of **{score}/10** for **{self.vendor_name}** has been recorded.\n"
            + (f'> "{comment}"' if comment else ""),
            ephemeral=True,
        )

        await interaction.client.update_live_embed(interaction.guild)


class Ratings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rate", description="Anonymously rate a vendor (1–10)")
    @app_commands.describe(
        vendor="The vendor to rate",
    )
    async def rate(self, interaction: discord.Interaction, vendor: str):
        db = self.bot.db
        vendor_row = await db.get_vendor_by_name(vendor, interaction.guild_id)

        if not vendor_row or vendor_row["status"] != "approved":
            approved = await db.get_approved_vendors(interaction.guild_id)
            names = ", ".join(f"**{v['name']}**" for v in approved) or "none yet"
            await interaction.response.send_message(
                f"**{vendor}** is not an approved vendor.\nApproved vendors: {names}",
                ephemeral=True,
            )
            return

        modal = RatingModal(vendor_row["id"], vendor_row["name"])
        await interaction.response.send_modal(modal)

    @rate.autocomplete("vendor")
    async def rate_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        vendors = await self.bot.db.get_approved_vendors(interaction.guild_id)
        return [
            app_commands.Choice(name=v["name"], value=v["name"])
            for v in vendors
            if current.lower() in v["name"].lower()
        ][:25]


async def setup(bot):
    await bot.add_cog(Ratings(bot))
