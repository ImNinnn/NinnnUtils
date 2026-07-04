from discord.ext.commands import Cog, Context, hybrid_group

async def setup(bot):
    await bot.add_cog(Ghosts(bot))

class Ghosts(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_message_delete(message):
        global message_cache, deleted_cache
        clean_cache()

        for msg in message_cache:
            if msg['id'] == message.id:
                deleted_msg = msg.copy()
                deleted_msg['deleted_at'] = datetime.now(timezone.utc)

                history_enabled = True
                ghost_enabled = False
                if message.guild:
                    guild_config, _ = get_guild_config(str(message.guild.id))
                    history_enabled = guild_config.get("edit_delete_history_enabled", True)
                    ghost_enabled = guild_config.get("ghost_ping_enabled", False)

                if history_enabled:
                    deleted_cache.append(deleted_msg)
                    deleted_cache = trim_cache(deleted_cache, max_len=10)
                if message.guild and not ghost_enabled:
                    break

                if msg['mentions'] and not msg['author'].bot:
                    pinged_users = [user for user in msg['mentions'] if user.id != msg['author'].id]
                    
                    if pinged_users:
                        settings = load_user_settings()
                        mentions_str = " ".join([format_user_reference(user, settings) for user in pinged_users])
                        author_str = format_user_reference(msg['author'], settings)
                        
                        embed = discord.Embed(
                            title="<:ghost:1517497569939558470> Ghost Ping Detected!",
                            description=f"{mentions_str}, you were pinged by {author_str} but the message was deleted.",
                            color=discord.Color.red()
                        )
                        if msg['content']:
                            embed.add_field(name="<:list:1517497572770451567> Deleted Content:", value=msg['content'], inline=False)
                        
                        embed.timestamp = msg['created_at']
                        
                        channel = bot.get_channel(msg['channel'])
                        if channel:
                            try:
                                await channel.send(embed=embed)
                            except discord.Forbidden as error:
                                add_bot_error_entry(message.guild.id if message.guild else None, msg['channel'], msg['author'], "ghost ping notification", error)
                break

    @Cog.listener()
    async def on_message_edit(before, after):
        if before.author.bot:
            return

        if before.content == after.content:
            return

        global message_cache, edited_cache
        clean_cache()

        history_enabled = True
        if before.guild:
            guild_config, _ = get_guild_config(str(before.guild.id))
            history_enabled = guild_config.get("edit_delete_history_enabled", True)

        for msg in message_cache:
            if msg['id'] == before.id:
                if history_enabled:
                    edited_msg = msg.copy()
                    
                    edited_msg['author_id'] = before.author.id
                    edited_msg['old_content'] = before.content if before.content else "*(Empty original content)*"
                    edited_msg['new_content'] = after.content if after.content else "*(Empty edited content)*"
                    edited_msg['jump_url'] = after.jump_url
                    edited_msg['edited_at'] = datetime.now(timezone.utc)
                    
                    edited_cache.append(edited_msg)
                    edited_cache = trim_cache(edited_cache, max_len=10)
                
                msg['content'] = after.content
                break
