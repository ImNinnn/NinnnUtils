from discord.ui import *
import discord

from Shared.Giveaways import load_giveaway_data, save_giveaway_data


class LeaveGiveawayConfirmView(View):
    def __init__(self, giveaway_id: str, original_message, user_id: str):
        super().__init__(timeout=60)
        self.giveaway_id = giveaway_id
        self.original_message = original_message
        self.user_id = user_id

    @discord.ui.button(label="Leave giveaway", style=discord.ButtonStyle.danger)
    async def confirm_leave(self, interaction: discord.Interaction, button: Button):
        data = load_giveaway_data()
        giveaway = data.get(self.giveaway_id)
        if not giveaway or giveaway.get('status') != 'active':
            await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
            return

        updated_entries = [entry for entry in giveaway.get('entries', []) if str(entry) != self.user_id]
        giveaway['entries'] = updated_entries
        data[self.giveaway_id] = giveaway
        save_giveaway_data(data)

        updated_view = GiveawayView(self.giveaway_id, giveaway)
        try:
            if self.original_message is not None:
                await self.original_message.edit(view=updated_view)
        except Exception:
            pass

        await interaction.response.send_message("You left the giveaway.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_leave(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Okay, you stayed in the giveaway.", ephemeral=True)


class GiveawayView(LayoutView):
    def __init__(self, giveaway_id: str, giveaway: dict, bot):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.giveaway = giveaway
        self.bot = bot
        self.build_components()

    def build_components(self):
        self.clear_items()
        giveaway = self.giveaway
        entries = giveaway.get('entries', [])

        entry_button = Button(
            label="Join / Leave",
            style=discord.ButtonStyle.success,
            custom_id=f"giveaway_enter:{self.giveaway_id}",
        )

        async def on_enter(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            data = load_giveaway_data()
            giveaway = data.get(self.giveaway_id)
            if not giveaway or giveaway.get('status') != 'active':
                await interaction.followup.send("This giveaway is no longer active.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            normalized_entries = [str(entry) for entry in giveaway.get('entries', []) if entry]
            if user_id in normalized_entries:
                confirm_view = LeaveGiveawayConfirmView(self.giveaway_id, interaction.message, user_id)
                await interaction.followup.send(
                    "You are already entered in this giveaway. Do you want to leave it?",
                    view=confirm_view,
                    ephemeral=True,
                )
                return

            normalized_entries.append(user_id)
            giveaway['entries'] = normalized_entries
            data[self.giveaway_id] = giveaway
            save_giveaway_data(data)

            updated_view = GiveawayView(self.giveaway_id, giveaway)
            try:
                await interaction.message.edit(view=updated_view)
            except Exception:
                pass

            await interaction.followup.send("You joined the giveaway!", ephemeral=True)

        entry_button.callback = on_enter

        host_id = giveaway.get('host_id')
        host_value = f"<@{host_id}>" if host_id else "Unknown"

        reward_parts = []
        if giveaway.get('role_id'):
            role = self.bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['role_id'])) if self.bot.get_guild(
                int(giveaway['guild_id'])) else None
            reward_parts.append(f"Role: {role.name if role else 'Unknown role'}")
        if giveaway.get('temp_role_id'):
            role = self.bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['temp_role_id'])) if self.bot.get_guild(
                int(giveaway['guild_id'])) else None
            reward_parts.append(
                f"Temp role: {role.name if role else 'Unknown role'} ({giveaway.get('temp_role_time', 0)}m)")
        if giveaway.get('item'):
            reward_parts.append(f"Item: {giveaway['item']}")
        if giveaway.get('money', 0):
            reward_parts.append(f"Money: ${giveaway['money']}")
        if giveaway.get('xp', 0):
            reward_parts.append(f"XP: {giveaway['xp']}")

        reward_text = "\n".join(reward_parts) if reward_parts else "No rewards"

        container_items = [
            TextDisplay(f"<:present:1522648005650415658> {giveaway['name']}"),
            Separator(),
            TextDisplay(f"**Host:** {host_value}\n**Winners:** {giveaway.get('winners_count', 1)}"),
        ]

        if giveaway.get('status') == 'active':
            container_items.append(
                Section(
                    f"**Entries:** {len(entries)}",
                    accessory=entry_button,
                )
            )
        else:
            container_items.append(TextDisplay(f"**Entries:** {len(entries)}"))

        container_items.extend([
            Separator(),
            TextDisplay(f"**Rewards:**\n{reward_text}"),
            Separator(),
            TextDisplay(f"**Ends:** <t:{giveaway.get('end_time')}:R>"),
        ])

        container = Container(
            *container_items,
            accent_color=discord.Color.gold() if giveaway.get('status') == 'active' else discord.Color.red(),
        )
        self.add_item(container)
