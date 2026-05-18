import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import build_vendor_list_embed


async def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    role_id = await interaction.client.db.get_config(interaction.guild_id, "admin_role_id")
    if role_id:
        role = interaction.guild.get_role(int(role_id))
        if role and role in interaction.user.roles:
            return True
    return False


def _resolve_channel(guild: discord.Guild, value: str) -> discord.TextChannel | None:
    """Resolve a channel from a mention, ID, or name string."""
    value = value.strip()
    if value.startswith("<#") and value.endswith(">"):
        value = value[2:-1]
    if value.isdigit():
        ch = guild.get_channel(int(value))
        return ch if isinstance(ch, discord.TextChannel) else None
    name = value.lstrip("#")
    return discord.utils.get(guild.text_channels, name=name)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="[Admin] Configure the bot for this server",
    )
    @app_commands.describe(
        live_channel="Type # and select the channel for the live vendor embed",
        admin_channel="Type # and select the channel for vendor suggestions (optional)",
        cooldown_days="Days a member must wait before rating the same vendor again (default 1)",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        live_channel: str,
        admin_channel: str = "",
        cooldown_days: app_commands.Range[int, 0, 365] = 1,
    ):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        live_ch = _resolve_channel(interaction.guild, live_channel)
        if not live_ch:
            await interaction.response.send_message(
                f"Could not find a text channel matching `{live_channel}`. "
                "Try typing the channel name exactly, e.g. `vendor-ratings`.",
                ephemeral=True,
            )
            return

        db = self.bot.db
        await db.set_config(interaction.guild_id, "live_channel_id", str(live_ch.id))
        await db.set_config(interaction.guild_id, "live_message_id", "")
        await db.set_config(interaction.guild_id, "cooldown_days", str(cooldown_days))

        lines = ["✅ Setup complete!", f"• Live embed → {live_ch.mention}"]

        if admin_channel:
            admin_ch = _resolve_channel(interaction.guild, admin_channel)
            if admin_ch:
                await db.set_config(interaction.guild_id, "admin_channel_id", str(admin_ch.id))
                lines.append(f"• Admin channel → {admin_ch.mention}")
            else:
                lines.append(f"• Admin channel → not found (skipped)")

        lines.append(f"• Rating cooldown → {cooldown_days} day(s)")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)
        await self.bot.update_live_embed(interaction.guild)

    @app_commands.command(name="vendors", description="Show the current vendor ratings list")
    async def vendors(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_vendor_stats(interaction.guild_id)
        embed = build_vendor_list_embed(stats)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(
        name="remove_rating",
        description="[Admin] Remove a specific rating by its ID",
    )
    @app_commands.describe(rating_id="The numeric ID of the rating to remove")
    async def remove_rating(self, interaction: discord.Interaction, rating_id: int):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        db = self.bot.db
        rating = await db.get_rating(rating_id, interaction.guild_id)
        if not rating:
            await interaction.response.send_message(
                f"No rating with ID **{rating_id}** found in this server.", ephemeral=True
            )
            return

        vendor = await db.get_vendor_by_id(rating["vendor_id"])
        await db.delete_rating(rating_id)

        await interaction.response.send_message(
            f"🗑️ Rating **#{rating_id}** (score: {rating['score']}/10"
            + (f", vendor: {vendor['name']}" if vendor else "")
            + ") has been removed.",
            ephemeral=True,
        )
        await self.bot.update_live_embed(interaction.guild)

    @app_commands.command(
        name="refresh",
        description="[Admin] Force-refresh the pinned vendor embed",
    )
    async def refresh(self, interaction: discord.Interaction):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        await interaction.response.send_message("Refreshing embed...", ephemeral=True)
        await self.bot.update_live_embed(interaction.guild)


async def setup(bot):
    await bot.add_cog(Admin(bot))
