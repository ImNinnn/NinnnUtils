from discord.ext.commands import Cog
from main import NinnnUtils

async def setup(bot):
    await bot.add_cog(UnEvents(bot))

class UnEvents(Cog):
    def __init__(self, bot: NinnnUtils):
        self.bot = bot

    @Cog.listener()
    async def cog_load(self):
        await self.bot.wait_until_ready()
        shard_info = (
            f"{len(self.bot.shards)} shard(s), IDs {list(self.bot.shards.keys())}"
            if self.bot.shards
            else "single process (no sharding)"
        )
        print(f"Logged in as {self.bot.user} (ID: {self.bot.user.id}) - {shard_info}")
        print(f"Serving {len(self.bot.guilds)} guild(s)")
        if not update_presence.is_running():
            update_presence.start()
        if not voice_xp_tracker.is_running():
            voice_xp_tracker.start()
        bot.loop.create_task(blacklist_startup_cleanup())

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        original_error = getattr(error, "original", error)
        bot_missing_permissions_error = getattr(app_commands, "BotMissingPermissions", None)

        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = error.retry_after
            if retry_after >= 60:
                minutes = int(retry_after // 60)
                seconds = int(retry_after % 60)
                if seconds > 0:
                    message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m {seconds}s** before trying again."
                else:
                    message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m** before trying again."
            else:
                retry_after = round(retry_after, 1)
                message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{retry_after}s** before trying again."
            if interaction.response.is_done():
                await interaction.followup.send(message_text, ephemeral=True)
            else:
                await interaction.response.send_message(message_text, ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> You lack the required permissions to run this: `{perms}`", ephemeral=True)
        elif bot_missing_permissions_error is not None and isinstance(error, bot_missing_permissions_error):
            perms = ", ".join(error.missing_permissions)
            message_text = f"<:disapprove:1517452151012589662> I am missing the required permissions to run this: `{perms}`"
            if interaction.response.is_done():
                await interaction.followup.send(message_text, ephemeral=True)
            else:
                await interaction.response.send_message(message_text, ephemeral=True)
        elif isinstance(original_error, discord.Forbidden):
            message_text = "<:disapprove:1517452151012589662> I am missing the permissions required to complete that action."
            if interaction.response.is_done():
                await interaction.followup.send(message_text, ephemeral=True)
            else:
                await interaction.response.send_message(message_text, ephemeral=True)
        else:
            add_bot_error(interaction, original_error)
            command_name = getattr(getattr(interaction, "command", None), "qualified_name", None) or getattr(getattr(interaction, "command", None), "name", "unknown command")
            print(f"Ignored exception in command tree [{command_name}]: {type(original_error).__name__}: {original_error}")
            print("".join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__)))
            if not interaction.response.is_done():
                await interaction.response.send_message("<:disapprove:1517452151012589662> An unexpected error occurred while executing this command.", ephemeral=True)
