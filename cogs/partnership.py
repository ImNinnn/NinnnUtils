import asyncio
import random
import discord
from discord.ext import commands

import save
from utils.user_settings import get_user_settings_entry


# Hardcoded partnership message
PARTNERSHIP_MESSAGE = (
    "-# Thanks DecibelNodes for making this project possible! Check them out at <https://decibelnodes.xyz> for a free way to host your Discord bot! \n-# /settings -> user settings to disable this"
)


class PartnershipCog(commands.Cog):
    """Show occasional ephemeral partnership messages alongside slash commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message = PARTNERSHIP_MESSAGE

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Only care about application commands
        try:
            if interaction.type is not discord.InteractionType.application_command:
                return
            
            # Ensure the interaction is specifically a Chat Input (slash) command,
            # ignoring User and Message Context Menu interactions.
            if interaction.data.get('type') != discord.AppCommandType.chat_input.value:
                return
        except Exception:
            return

        if not interaction.user or getattr(interaction.user, 'bot', False):
            return

        # Respect user setting if they disabled ads
        try:
            settings = save.load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            if user_settings.get('disable_ads'):
                return
        except Exception:
            pass

        # 20% chance
        try:
            if random.random() >= 0.2:
                return
        except Exception:
            return

        # schedule sending the ephemeral ad after the command has responded
        asyncio.create_task(self._send_ephemeral_after_response(interaction))

    async def _send_ephemeral_after_response(self, interaction: discord.Interaction):
        # wait for the original command to have an initial response (or a short timeout)
        try:
            waited = 0.0
            while not interaction.response.is_done() and waited < 5.0:
                await asyncio.sleep(0.1)
                waited += 0.1
        except Exception:
            pass

        message = getattr(self, 'message', PARTNERSHIP_MESSAGE) or ''
        if not message:
            return

        try:
            await interaction.followup.send(message, ephemeral=True)
        except Exception as exc:
            print(f"[partnership] failed to send ad followup: {exc}")


async def setup(bot: commands.Bot):
    await bot.add_cog(PartnershipCog(bot))