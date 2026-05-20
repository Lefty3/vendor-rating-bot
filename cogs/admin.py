import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import build_vendor_list_embed


async def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.permissions.administrator:
        return True
    role_id = await interaction.client.db.get_config(interaction.guild_id, "admin_role_id")
    if role_id:
        role = interaction.guild.get_role(int(role_id))
        if role and role in interaction.user.roles:
            return True
    return False


async def _resolve_channel(guild: discord.Guild, value: str) -> discord.TextChannel | None:
    """Resolve a channel from a mention, ID, or name string."""
    value = value.strip()
    if value.startswith("<#") and value.endswith(">"):
        value = value[2:-1]
    if value.isdigit():
        ch = guild.get_channel(int(value))
        if ch is None:
            try:
                ch = await guild.fetch_channel(int(value))
                print(f"[setup] fetched channel via API: {ch} (type={type(ch).__name__})")
            except discord.Forbidden:
                print(f"[setup] Forbidden fetching channel {value} — bot lacks View Channel permission")
                return None
            except discord.NotFound:
                print(f"[setup] Channel {value} not found")
                return None
            except Exception as e:
                print(f"[setup] Unexpected error fetching channel {value}: {e}")
                return None
        return ch if isinstance(ch, discord.TextChannel) else None
    name = value.lstrip("#")
    ch = discord.utils.get(guild.text_channels, name=name)
    print(f"[setup] name lookup '{name}' → {ch}")
    return ch


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

        live_ch = await _resolve_channel(interaction.guild, live_channel)
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
        env_lines = [
            "**Save these as Railway Variables so settings survive redeploys:**",
            f"`LIVE_CHANNEL_ID` = `{live_ch.id}`",
        ]

        if admin_channel:
            admin_ch = await _resolve_channel(interaction.guild, admin_channel)
            if admin_ch:
                await db.set_config(interaction.guild_id, "admin_channel_id", str(admin_ch.id))
                lines.append(f"• Admin channel → {admin_ch.mention}")
                env_lines.append(f"`ADMIN_CHANNEL_ID` = `{admin_ch.id}`")
            else:
                lines.append(f"• Admin channel → not found (skipped)")

        lines.append(f"• Rating cooldown → {cooldown_days} day(s)")
        lines.append("")
        lines.extend(env_lines)

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
        name="remove_vendor",
        description="[Admin] Permanently remove an approved vendor and all its ratings",
    )
    @app_commands.describe(name="Name of the approved vendor to remove")
    async def remove_vendor(self, interaction: discord.Interaction, name: str):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        db = self.bot.db
        vendor = await db.get_vendor_by_name(name, interaction.guild_id)
        if not vendor or vendor["status"] != "approved":
            await interaction.response.send_message(
                f"No approved vendor named **{name}** found.", ephemeral=True
            )
            return

        await db.delete_vendor(vendor["id"], interaction.guild_id)
        await interaction.response.send_message(
            f"🗑️ **{vendor['name']}** has been removed from the vendor list.",
            ephemeral=True,
        )
        await self.bot.update_live_embed(interaction.guild)

    @remove_vendor.autocomplete("name")
    async def remove_vendor_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        approved = await self.bot.db.get_approved_vendors(interaction.guild_id)
        return [
            app_commands.Choice(name=v["name"], value=v["name"])
            for v in approved
            if current.lower() in v["name"].lower()
        ][:25]

    @app_commands.command(
        name="rename_vendor",
        description="[Admin] Rename a vendor; merges into target if the new name already exists",
    )
    @app_commands.describe(
        old_name="Current vendor name",
        new_name="New display name for the vendor",
    )
    async def rename_vendor(
        self, interaction: discord.Interaction, old_name: str, new_name: str
    ):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        new_name = new_name.strip()
        if len(new_name) < 2:
            await interaction.response.send_message(
                "New name must be at least 2 characters.", ephemeral=True
            )
            return

        db = self.bot.db
        source = await db.get_vendor_by_name(old_name, interaction.guild_id)
        if not source:
            await interaction.response.send_message(
                f"No vendor named **{old_name}** found.", ephemeral=True
            )
            return

        new_lower = new_name.lower()

        # Case-only change on the same vendor — just update display name.
        if new_lower == source["name_lower"]:
            await db.rename_vendor(source["id"], new_name, update_name_lower=False)
            await interaction.response.send_message(
                f"✏️ Display name updated to **{new_name}**.", ephemeral=True
            )
            await self.bot.update_live_embed(interaction.guild)
            return

        target = await db.get_vendor_by_name(new_name, interaction.guild_id)
        if target and target["id"] != source["id"]:
            await db.merge_vendors(source["id"], target["id"])
            await interaction.response.send_message(
                f"🔀 Merged **{source['name']}** into existing **{target['name']}** "
                "(ratings transferred).",
                ephemeral=True,
            )
        else:
            await db.rename_vendor(source["id"], new_name, update_name_lower=True)
            await interaction.response.send_message(
                f"✏️ **{source['name']}** renamed to **{new_name}**.", ephemeral=True
            )

        await self.bot.update_live_embed(interaction.guild)

    @rename_vendor.autocomplete("old_name")
    async def rename_vendor_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        approved = await self.bot.db.get_approved_vendors(interaction.guild_id)
        return [
            app_commands.Choice(name=v["name"], value=v["name"])
            for v in approved
            if current.lower() in v["name"].lower()
        ][:25]

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
