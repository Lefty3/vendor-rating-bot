import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import build_suggestion_embed


async def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.permissions.administrator:
        return True
    role_id = await interaction.client.db.get_config(interaction.guild_id, "admin_role_id")
    if role_id:
        role = interaction.guild.get_role(int(role_id))
        if role and role in interaction.user.roles:
            return True
    return False


class VendorApprovalView(discord.ui.View):
    """Persistent view — survives bot restarts via custom_id encoding."""

    def __init__(self, vendor_id: int):
        super().__init__(timeout=None)
        self.vendor_id = vendor_id

        approve = discord.ui.Button(
            label="Approve",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"vendor_approve_{vendor_id}",
        )
        approve.callback = self._approve

        reject = discord.ui.Button(
            label="Reject",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"vendor_reject_{vendor_id}",
        )
        reject.callback = self._reject

        self.add_item(approve)
        self.add_item(reject)

    async def _approve(self, interaction: discord.Interaction):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        db = interaction.client.db
        vendor = await db.get_vendor_by_id(self.vendor_id)
        if not vendor or vendor["status"] != "pending":
            await interaction.response.send_message(
                "This vendor has already been reviewed.", ephemeral=True
            )
            return

        await db.update_vendor_status(self.vendor_id, "approved", interaction.user.id)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Approved by {interaction.user.display_name}")

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.client.update_live_embed(interaction.guild)

    async def _reject(self, interaction: discord.Interaction):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        db = interaction.client.db
        vendor = await db.get_vendor_by_id(self.vendor_id)
        if not vendor or vendor["status"] != "pending":
            await interaction.response.send_message(
                "This vendor has already been reviewed.", ephemeral=True
            )
            return

        await db.update_vendor_status(self.vendor_id, "rejected", interaction.user.id)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ Rejected by {interaction.user.display_name}")

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)


class Vendors(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="suggest", description="Suggest a new vendor for the community list")
    @app_commands.describe(name="Vendor name to suggest")
    async def suggest(self, interaction: discord.Interaction, name: str):
        if len(name.strip()) < 2:
            await interaction.response.send_message(
                "Vendor name must be at least 2 characters.", ephemeral=True
            )
            return

        db = self.bot.db
        created = await db.suggest_vendor(name, interaction.user.id, interaction.guild_id)

        if not created:
            await interaction.response.send_message(
                f"**{name}** is already on the vendor list (pending or approved).",
                ephemeral=True,
            )
            return

        vendor = await db.get_vendor_by_name(name, interaction.guild_id)

        await interaction.response.send_message(
            f"Thanks! **{name}** has been submitted for admin review.", ephemeral=True
        )

        # Post approval card to admin channel
        admin_channel_id = await db.get_config(interaction.guild_id, "admin_channel_id")
        if admin_channel_id:
            channel = interaction.guild.get_channel(int(admin_channel_id))
            if channel:
                view = VendorApprovalView(vendor["id"])
                self.bot.add_view(view)
                embed = build_suggestion_embed(name, interaction.user, vendor["id"])
                await channel.send(embed=embed, view=view)

    # Slash command fallbacks for admins who prefer typing
    @app_commands.command(name="approve", description="[Admin] Approve a pending vendor suggestion")
    @app_commands.describe(name="Vendor name to approve")
    async def approve(self, interaction: discord.Interaction, name: str):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        vendor = await self.bot.db.get_vendor_by_name(name, interaction.guild_id)
        if not vendor:
            await interaction.response.send_message(
                f"No vendor named **{name}** found.", ephemeral=True
            )
            return
        if vendor["status"] == "approved":
            await interaction.response.send_message(
                f"**{name}** is already approved.", ephemeral=True
            )
            return

        await self.bot.db.update_vendor_status(vendor["id"], "approved", interaction.user.id)
        await interaction.response.send_message(
            f"✅ **{name}** has been approved and added to the vendor list.", ephemeral=True
        )
        await self.bot.update_live_embed(interaction.guild)

    @approve.autocomplete("name")
    async def approve_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        pending = await self.bot.db.get_pending_vendors(interaction.guild_id)
        return [
            app_commands.Choice(name=v["name"], value=v["name"])
            for v in pending
            if current.lower() in v["name"].lower()
        ][:25]

    @app_commands.command(name="reject", description="[Admin] Reject a pending vendor suggestion")
    @app_commands.describe(name="Vendor name to reject")
    async def reject(self, interaction: discord.Interaction, name: str):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        vendor = await self.bot.db.get_vendor_by_name(name, interaction.guild_id)
        if not vendor or vendor["status"] == "approved":
            await interaction.response.send_message(
                f"No pending vendor named **{name}** found.", ephemeral=True
            )
            return

        await self.bot.db.update_vendor_status(vendor["id"], "rejected", interaction.user.id)
        await interaction.response.send_message(
            f"❌ **{name}** has been rejected.", ephemeral=True
        )

    @reject.autocomplete("name")
    async def reject_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        pending = await self.bot.db.get_pending_vendors(interaction.guild_id)
        return [
            app_commands.Choice(name=v["name"], value=v["name"])
            for v in pending
            if current.lower() in v["name"].lower()
        ][:25]

    @app_commands.command(name="pending", description="[Admin] List vendors awaiting approval")
    async def pending(self, interaction: discord.Interaction):
        if not await _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        vendors = await self.bot.db.get_pending_vendors(interaction.guild_id)
        if not vendors:
            await interaction.response.send_message(
                "No pending vendor suggestions.", ephemeral=True
            )
            return

        lines = [f"**{v['name']}** (ID: {v['id']})" for v in vendors]
        await interaction.response.send_message(
            "**Pending vendor suggestions:**\n" + "\n".join(lines), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Vendors(bot))
