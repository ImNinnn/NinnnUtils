from discord.ext.commands import Cog, Context, hybrid_group

async def setup(bot):
    await bot.add_cog(Welcomer(bot))

class Welcomer(Cog):
    def __init__(self, bot):
        self.bot = bot

    @bot.event
    async def on_member_join(member):
        guild_config, _ = get_guild_config(str(member.guild.id))
        channel_id = guild_config.get("welcome_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                try:
                    welcome_file = await create_welcome_card(member)
                    await channel.send(f"Welcome {format_user_reference(member)}!", file=welcome_file)
                except discord.Forbidden as error:
                    add_bot_error_entry(member.guild.id, channel.id, member, "welcome banner", error)
                except Exception as e:
                    print(f"Error creating welcome card: {e}")


    @bot.event
    async def on_member_remove(member):
        guild_config, _ = get_guild_config(str(member.guild.id))
        channel_id = guild_config.get("goodbye_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                try:
                    goodbye_file = await create_goodbye_card(member)
                    await channel.send(f"Goodbye {member.display_name}. We'll miss you!", file=goodbye_file)
                except discord.Forbidden as error:
                    add_bot_error_entry(member.guild.id, channel.id, member, "goodbye banner", error)
                except Exception as e:
                    print(f"Error creating goodbye card: {e}")
