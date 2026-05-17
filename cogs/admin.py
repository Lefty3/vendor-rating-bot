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


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="[Admin] Configure the bot for this server",
    )
    @app_commands.describe(
        live_channel="Channel where the live vendor embed will be posted and pinned",
        admin_channel="Channel where vendor suggestions are posted for review (optional)",
        admin_role="Role that can approve/reject vendors in addition to server admins (optional)",
        cooldown_days="Days a member must wait before rating the same vendor again (default 1)",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        live_channel: discord.TextChannel,
        admin_channel: discord.TextChannel | None = None,
        admin_role: discord.Role | None = None,
        cooldown_days: app_commands.Range[int, 0, 365] = 1,
    ):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        db = self.bot.db
        await db.set_config(interaction.guild_id, "live_channel_id", str(live_channel.id))
        # Reset message ID so a fresh embed is posted
        await db.set_config(interaction.guild_id, "live_message_id", "")
        await db.set_config(interaction.guild_id, "cooldown_days", str(cooldown_days))

        if admin_channel:
            await db.set_config(interaction.guild_id, "admin_channel_id", str(admin_channel.id))
        if admin_role:
            await db.set_config(interaction.guild_id, "admin_role_id", str(admin_role.id))

        lines = [
            f"✅ Setup complete!",
            f"• Live embed → {live_channel.mention}",
        ]
        if admin_channel:
            lines.append(f"• Admin channel → {admin_channel.mention}")
        if admin_role:
            lines.append(f"• Admin role → {admin_role.mention}")
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
