import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from db import Database
from utils.embeds import build_vendor_list_embed

load_dotenv()

COGS = ("cogs.ratings", "cogs.vendors", "cogs.admin")


class VendorBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database()

    async def setup_hook(self):
        await self.db.init()

        for cog in COGS:
            await self.load_extension(cog)

        # Re-register persistent approval views so buttons survive restarts
        from cogs.vendors import VendorApprovalView

        for guild in self.guilds:
            pending = await self.db.get_pending_vendors(guild.id)
            for vendor in pending:
                self.add_view(VendorApprovalView(vendor["id"]))

        await self.tree.sync()

    async def on_ready(self):
        print(f"Ready: {self.user}  (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="vendor ratings | /rate /suggest",
            )
        )

    async def update_live_embed(self, guild: discord.Guild):
        """Edit the pinned embed in the configured live channel."""
        channel_id = await self.db.get_config(guild.id, "live_channel_id")
        if not channel_id:
            return

        channel = guild.get_channel(int(channel_id))
        if not channel:
            return

        stats = await self.db.get_vendor_stats(guild.id)
        embed = build_vendor_list_embed(stats)

        message_id = await self.db.get_config(guild.id, "live_message_id")
        if message_id:
            try:
                msg = await channel.fetch_message(int(message_id))
                await msg.edit(embed=embed)
                return
            except (discord.NotFound, discord.Forbidden):
                pass

        msg = await channel.send(embed=embed)
        await self.db.set_config(guild.id, "live_message_id", str(msg.id))
        try:
            await msg.pin()
        except discord.Forbidden:
            pass


bot = VendorBot()
bot.run(os.getenv("DISCORD_TOKEN"))
