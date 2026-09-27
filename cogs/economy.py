"""Economy: wallets, shop, inventory, crafting, item uses, trading and the economy settings panel."""

import asyncio
import random
import re

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, Modal, Section, Separator, TextDisplay, TextInput

from save import load_data, save_data
from utils.audit import add_bot_error_entry
from utils.economy import (
    MAX_ITEM_BATCH_SIZE,
    ensure_economy_enabled,
    find_item_key,
    get_guild_data,
    get_user_data,
    inventory_add,
    inventory_count,
    inventory_remove,
    normalize_item,
    parse_item_amount_entry,
    validate_item_batch_amount,
)
from utils.formatting import format_user_reference
from utils.permissions import validate_role_selection
from utils.views import EconomyChoiceView, TimeoutDisabledLayoutView, TimeoutDisabledView


class ShopView(TimeoutDisabledLayoutView):
    def __init__(self, shop_items, guild_id, user_id):
        super().__init__(timeout=600)
        self.shop_items = dict(shop_items)
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = 0
        self.items_per_page = 5
        self.build_components()

    def build_components(self):
        self.clear_items()

        items = list(self.shop_items.items())
        total_pages = max(1, (len(items) + self.items_per_page - 1) // self.items_per_page)
        start = self.current_page * self.items_per_page
        page_items = items[start:start + self.items_per_page]

        container_parts = [
            TextDisplay("## <:chalice:1517579767573123092> Server Shop"),
            TextDisplay("Choose an item from the menu below and buy it with the button."),
            Separator(),
            TextDisplay(f"Page {self.current_page + 1}/{total_pages}"),
        ]

        for item_name, info in page_items:
            buy_button = Button(
                label=f"Buy ${info['price']}",
                style=discord.ButtonStyle.primary,
                custom_id=f"shop_buy:{item_name}",
            )

            async def buy_callback(interaction: discord.Interaction, button: Button = None, item_name=item_name, info=info):
                data = load_data()
                user_data = get_user_data(data, self.guild_id, str(interaction.user.id))
                price = info['price']

                if user_data["balance"] < price:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> You can't afford this!", ephemeral=True)
                    return

                user_data["balance"] -= price
                inventory_add(user_data["inventory"], item_name)
                save_data(data)

                self.build_components()
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(f"<:approve:1517452125687513158> You bought **{item_name}**!", ephemeral=True)

            buy_button.callback = buy_callback
            container_parts.append(
                Section(
                    f"**{item_name}**\n{str(info.get('desc', 'No description provided')).strip() or 'No description provided'}",
                    accessory=buy_button,
                )
            )

        data = load_data()
        user_data = get_user_data(data, self.guild_id, str(self.user_id))
        balance = user_data.get("balance", 0)

        container_parts.extend([
            Separator(),
            TextDisplay(f"<:money:1517580310395486239> Your balance: **${balance}**"),
        ])

        container = Container(*container_parts, accent_color=discord.Color.gold())
        self.add_item(container)

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="shop_prev", disabled=self.current_page == 0)
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="shop_next", disabled=self.current_page >= total_pages - 1)

        async def prev_callback(interaction: discord.Interaction):
            if self.current_page > 0:
                self.current_page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_callback(interaction: discord.Interaction):
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        prev_button.callback = prev_callback
        next_button.callback = next_callback
        self.add_item(discord.ui.ActionRow(prev_button, next_button))


class TradeItemModal(Modal):
    def __init__(self, trade_view, user_id: str):
        super().__init__(title="Trade Item")
        self.trade_view = trade_view
        self.user_id = user_id
        self.action_input = TextInput(label="Action (add/remove)", placeholder="add or remove", required=True, max_length=10)
        self.item_input = TextInput(label="Item name", placeholder="Item name", required=True)
        self.amount_input = TextInput(label="Amount", placeholder="1", required=True, max_length=10)
        self.add_item(self.action_input)
        self.add_item(self.item_input)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action_input.value.strip().lower()
        if action not in ("add", "remove"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be add or remove.", ephemeral=True)
            return

        item_name = normalize_item(self.item_input.value)
        try:
            amount = int(self.amount_input.value.strip())
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be a number.", ephemeral=True)
            return

        if amount <= 0 or amount > MAX_ITEM_BATCH_SIZE:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Amount must be between 1 and {MAX_ITEM_BATCH_SIZE}.",
                ephemeral=True,
            )
            return

        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), self.user_id)
        offer = self.trade_view.offers[self.user_id]

        if action == "add":
            available = inventory_count(user_data["inventory"], item_name)
            if available < amount:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:disapprove:1517452151012589662> You only have {available}x {item_name} available to add.",
                    ephemeral=True,
                )
                return
            offer["items"][item_name] = offer["items"].get(item_name, 0) + amount
        else:
            current = offer["items"].get(item_name, 0)
            if current < amount:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:disapprove:1517452151012589662> Your offer only contains {current}x {item_name}.",
                    ephemeral=True,
                )
                return
            if amount == current:
                offer["items"].pop(item_name, None)
            else:
                offer["items"][item_name] = current - amount

        self.trade_view.reset_acceptances()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Your trade offer has been updated.", ephemeral=True)
        await self.trade_view.refresh_trade_message()


class TradeMoneyModal(Modal):
    def __init__(self, trade_view, user_id: str, max_money: int):
        super().__init__(title="Trade Money")
        self.trade_view = trade_view
        self.user_id = user_id
        self.max_money = max_money
        self.money_input = TextInput(label=f"Money (0 - {max_money})", placeholder="0", required=True, max_length=12)
        self.add_item(self.money_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.money_input.value.strip())
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be a number.", ephemeral=True)
            return

        if amount < 0 or amount > self.max_money:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Amount must be between 0 and {self.max_money}.",
                ephemeral=True,
            )
            return

        self.trade_view.offers[self.user_id]["money"] = amount
        self.trade_view.reset_acceptances()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Your trade money offer has been updated.", ephemeral=True)
        await self.trade_view.refresh_trade_message()


class TradeView(TimeoutDisabledLayoutView):
    def __init__(self, initiator: discord.Member, partner: discord.Member):
        super().__init__(timeout=600)
        self.initiator_id = str(initiator.id)
        self.partner_id = str(partner.id)
        self.initiator_name = initiator.display_name
        self.partner_name = partner.display_name
        self.offers = {
            self.initiator_id: {"items": {}, "money": 0, "status": "pending"},
            self.partner_id: {"items": {}, "money": 0, "status": "pending"},
        }
        self.trade_message = None
        self.trade_ended = False

        self.items_button = Button(label="Items", style=discord.ButtonStyle.secondary)
        self.money_button = Button(label="Money", style=discord.ButtonStyle.secondary)
        self.accept_button = Button(label="Accept", style=discord.ButtonStyle.success)
        self.decline_button = Button(label="Decline", style=discord.ButtonStyle.danger)

        self.items_button.callback = self.on_items_clicked
        self.money_button.callback = self.on_money_clicked
        self.accept_button.callback = self.on_accept_clicked
        self.decline_button.callback = self.on_decline_clicked

        self.refresh_view()

    def refresh_view(self):
        self.clear_items()
        self.add_item(self.build_container())
        self.add_item(discord.ui.ActionRow(self.items_button, self.money_button))
        self.add_item(discord.ui.ActionRow(self.accept_button, self.decline_button))
        self.update_button_states()

    def update_button_states(self):
        disabled = self.trade_ended
        self.items_button.disabled = disabled
        self.money_button.disabled = disabled
        self.accept_button.disabled = disabled
        self.decline_button.disabled = disabled

    def get_status_emoji(self, user_id: str) -> str:
        status = self.offers[user_id]["status"]
        if status == "accepted":
            return "<:approve:1517452125687513158>"
        if status == "declined":
            return "<:disapprove:1517452151012589662>"
        return "<:warning:1517452174991556758>"

    def format_offer_lines(self, user_id: str) -> list[str]:
        offer = self.offers[user_id]
        lines = []
        if offer["items"]:
            for item_name, amount in offer["items"].items():
                lines.append(f"• {item_name} ×{amount}")
        else:
            lines.append("• _(no items offered)_")
        lines.append(f"• Money: **${offer['money']}**")
        return lines

    def build_container(self) -> Container:
        initiator_emoji = self.get_status_emoji(self.initiator_id)
        partner_emoji = self.get_status_emoji(self.partner_id)

        status_lines = []
        if self.trade_ended:
            if any(offer["status"] == "declined" for offer in self.offers.values()):
                declined_users = [
                    self.initiator_name if self.offers[self.initiator_id]["status"] == "declined" else self.partner_name,
                ]
                status_lines.append(TextDisplay(f"<:disapprove:1517452151012589662> Trade declined by {', '.join(declined_users)}. The offer has been closed."))
            else:
                status_lines.append(TextDisplay("<:approve:1517452125687513158> The trade has been completed successfully!"))
        else:
            accepted = [
                self.initiator_name if self.offers[self.initiator_id]["status"] == "accepted" else None,
                self.partner_name if self.offers[self.partner_id]["status"] == "accepted" else None,
            ]
            accepted = [name for name in accepted if name]
            pending = [
                self.initiator_name if self.offers[self.initiator_id]["status"] == "pending" else None,
                self.partner_name if self.offers[self.partner_id]["status"] == "pending" else None,
            ]
            pending = [name for name in pending if name]

            if accepted and pending:
                status_lines.append(TextDisplay(f"<:warning:1517452174991556758> {', '.join(accepted)} accepted. Waiting on {', '.join(pending)}."))
            elif accepted and not pending:
                status_lines.append(TextDisplay("<:approve:1517452125687513158> Both users have accepted. Finalizing trade..."))
            else:
                status_lines.append(TextDisplay("<:warning:1517452174991556758> Trade pending. Add items or money, then both users must accept."))

        lines = [
            TextDisplay(f"## <:loop:1518977798939742449> Trade"),
            *status_lines,
            Separator(),
            TextDisplay(f"{initiator_emoji} {self.initiator_name}'s offer:"),
        ]
        lines.extend(TextDisplay(line) for line in self.format_offer_lines(self.initiator_id))
        lines.append(Separator())
        lines.append(TextDisplay(f"{partner_emoji} {self.partner_name}'s offer:"))
        lines.extend(TextDisplay(line) for line in self.format_offer_lines(self.partner_id))

        return Container(*lines, accent_color=discord.Color.blue())

    async def refresh_trade_message(self):
        self.refresh_view()
        if self.trade_message:
            await self.trade_message.edit(view=self)

    def reset_acceptances(self):
        for offer in self.offers.values():
            if offer["status"] != "declined":
                offer["status"] = "pending"

    async def on_items_clicked(self, interaction: discord.Interaction):
        if str(interaction.user.id) not in self.offers:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        await interaction.response.send_modal(TradeItemModal(self, str(interaction.user.id)))

    async def on_money_clicked(self, interaction: discord.Interaction):
        if str(interaction.user.id) not in self.offers:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        max_money = get_user_data(load_data(), str(interaction.guild.id), str(interaction.user.id))["balance"]
        await interaction.response.send_modal(TradeMoneyModal(self, str(interaction.user.id), max_money))

    async def on_accept_clicked(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in self.offers:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        if self.trade_ended:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> This trade has already ended.", ephemeral=True)

        self.offers[user_id]["status"] = "accepted"
        await self.refresh_trade_message()

        if all(offer["status"] == "accepted" for offer in self.offers.values()):
            await self.complete_trade(interaction)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:warning:1517452174991556758> Trade accepted. Waiting for the other user.", ephemeral=True)

    async def on_decline_clicked(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in self.offers:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        if self.trade_ended:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> This trade has already ended.", ephemeral=True)

        self.offers[user_id]["status"] = "declined"
        self.trade_ended = True
        await self.refresh_trade_message()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You declined the trade.", ephemeral=True)

    async def complete_trade(self, interaction: discord.Interaction):
        data = load_data()
        guild_id = str(interaction.guild.id)
        sender_id, receiver_id = self.initiator_id, self.partner_id
        sender_data = get_user_data(data, guild_id, sender_id)
        receiver_data = get_user_data(data, guild_id, receiver_id)

        for user_id, offer in self.offers.items():
            if user_id == self.initiator_id:
                counterparty_id = self.partner_id
            else:
                counterparty_id = self.initiator_id
            counterparty_data = get_user_data(data, guild_id, counterparty_id)
            for item_name, amount in offer["items"].items():
                if inventory_count(get_user_data(data, guild_id, user_id)["inventory"], item_name) < amount:
                    self.reset_acceptances()
                    await self.refresh_trade_message()
                    await interaction.response.defer(ephemeral=True)
                    return await interaction.followup.send(
                        f"<:disapprove:1517452151012589662> Trade failed because {format_user_reference(interaction.guild.get_member(int(user_id)) or interaction.user)} no longer has enough {item_name}.",
                        ephemeral=True,
                    )
            if get_user_data(data, guild_id, user_id)["balance"] < offer["money"]:
                self.reset_acceptances()
                await self.refresh_trade_message()
                await interaction.response.defer(ephemeral=True)
                return await interaction.followup.send(
                    f"<:disapprove:1517452151012589662> Trade failed because {format_user_reference(interaction.guild.get_member(int(user_id)) or interaction.user)} no longer has enough money.",
                    ephemeral=True,
                )

        for user_id, offer in self.offers.items():
            counterparty_id = self.partner_id if user_id == self.initiator_id else self.initiator_id
            counterparty_data = get_user_data(data, guild_id, counterparty_id)
            for item_name, amount in offer["items"].items():
                inventory_remove(get_user_data(data, guild_id, user_id)["inventory"], item_name, amount)
                inventory_add(counterparty_data["inventory"], item_name, amount)
            get_user_data(data, guild_id, user_id)["balance"] -= offer["money"]
            counterparty_data["balance"] += offer["money"]

        save_data(data)
        self.trade_ended = True
        await self.refresh_trade_message()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Trade completed successfully.", ephemeral=True)

    async def on_timeout(self):
        if self.trade_ended:
            return
                                                  
        for offer in self.offers.values():
            offer["status"] = "declined"
        self.trade_ended = True
        try:
            await super().on_timeout()
        except Exception:
            pass
                                                           
        try:
            await self.refresh_trade_message()
        except Exception:
            pass
                                                         
        msg = self.trade_message or self._get_timeout_message()
        if msg is not None:
            try:
                await msg.channel.send("<:disapprove:1517452151012589662> Trade auto-declined due to inactivity.")
            except Exception:
                pass


class EconomyRoleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, item_name: str, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.item_name = item_name
        self.settings_message = settings_message
        self.callback = callback
        self.is_temp_role = is_temp_role
        self.role_select = None

        role_options = []
        for role in sorted(guild.roles, key=lambda r: (r.position, r.name), reverse=True):
            if role.is_default():
                continue
            role_options.append(discord.SelectOption(label=role.name[:100], value=str(role.id)))

        if role_options:
            self.role_select = discord.ui.Select(
                placeholder=prompt,
                options=role_options[:25],
                min_values=1,
                max_values=1,
                custom_id=f"economy_role_select_{'temp' if is_temp_role else 'normal'}",
            )
            self.role_select.callback = self.on_role_selected
            self.add_item(self.role_select)

        self.no_button = Button(label="No", style=discord.ButtonStyle.secondary, custom_id=f"economy_role_none_{'temp' if is_temp_role else 'normal'}")
        self.no_button.callback = self.on_no_selected
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        role_id = int(self.role_select.values[0])
        await self.callback(interaction, role_id, self.item_name, self.settings_message, self.is_temp_role)

    async def on_no_selected(self, interaction: discord.Interaction):
        await self.callback(interaction, None, self.item_name, self.settings_message, self.is_temp_role)


class EconomySettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        shop_items = guild.get("shop", {})
        uses_items = guild.get("item_uses", {})
        priced_items = guild.get("item_values", {})
        recipes = guild.get("recipes", {})

        self.shop_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_shop_edit")
        self.uses_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_uses_edit")
        self.prices_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_prices_edit")
        self.crafts_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_crafts_edit")

        self.shop_button.callback = self.handle_shop_edit
        self.uses_button.callback = self.handle_uses_edit
        self.prices_button.callback = self.handle_prices_edit
        self.crafts_button.callback = self.handle_crafts_edit

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="economy_settings_back")
        self.back_button.callback = self.handle_back

        shop_summary = ", ".join(list(shop_items.keys())[:6]) if shop_items else "None"
        uses_summary = ", ".join(list(uses_items.keys())[:6]) if uses_items else "None"
        prices_summary = ", ".join(list(priced_items.keys())[:6]) if priced_items else "None"
        crafts_summary = ", ".join(list(recipes.keys())[:6]) if recipes else "None"

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Economy settings**"),
            TextDisplay("Configure the economy systems below."),
            Separator(),
            Section(f"<:money:1517580310395486239> Shop items\n{shop_summary}", accessory=self.shop_button),
            Section(f"<:Vial:1517681553377857628> Item uses\n{uses_summary}", accessory=self.uses_button),
            Section(f"<:money:1517580310395486239> Item prices\n{prices_summary}", accessory=self.prices_button),
            Section(f"<:craft:1518348021161660539> Crafting recipes\n{crafts_summary}", accessory=self.crafts_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass
        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def handle_back(self, interaction: discord.Interaction):
        from cogs.settings import GuildSettingsMenuView  # imported here: cogs.settings imports this cog

        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_shop_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Shop items?",
            view=EconomyChoiceView(self.user_id, self.open_shop_add, self.open_shop_remove, "shop", self.open_shop_edit, settings_message),
            ephemeral=True,
        )

    async def open_shop_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopAddModal(self.add_shop_item, self.guild_id, settings_message))

    async def open_shop_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_shop_edit_launch, self.guild_id, "shop", settings_message))

    async def open_shop_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
                                                                                               
        view = ShopEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Item found. Click below to continue editing.", view=view, ephemeral=True)

    async def _apply_shop_edit(self, original_key: str, interaction: discord.Interaction, name: str, desc: str, price: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("shop", {})
        new_key = normalize_item(name)
                                   
        if new_key != original_key and original_key in guild.get("shop", {}):
            try:
                del guild["shop"][original_key]
            except KeyError:
                pass
        guild["shop"][new_key] = {"desc": desc, "price": price}
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Shop item **{new_key}** updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def open_shop_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopRemoveModal(self.remove_shop_item, self.guild_id, settings_message))

    async def add_shop_item(self, interaction: discord.Interaction, name: str, desc: str, price: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("shop", {})
        guild["shop"][normalize_item(name)] = {"desc": desc, "price": price}
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Shop item **{normalize_item(name)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_shop_item(self, interaction: discord.Interaction, name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("shop", {})
        canonical = find_item_key(guild.get("shop", {}), name)
        if canonical:
            del guild["shop"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed shop item **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No shop item found for **{name}**.", ephemeral=True)

    async def handle_uses_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Item uses?",
            view=EconomyChoiceView(self.user_id, self.open_uses_add, self.open_uses_remove, "uses", self.open_uses_edit, settings_message),
            ephemeral=True,
        )

    async def open_uses_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseAddModal(self.add_use_item, self.guild_id, settings_message))

    async def open_uses_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseRemoveModal(self.remove_use_item, self.guild_id, settings_message))

    async def open_uses_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_use_edit_launch, self.guild_id, "uses", settings_message))

    async def open_use_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
        view = UseEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Use effect found. Click below to continue editing.", view=view, ephemeral=True)

    async def add_use_item(self, interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message: discord.Message | None):
        item_name = normalize_item(item)
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_uses", {})
        guild["item_uses"][item_name] = {
            "money": money,
            "xp": xp,
            "message": message or "Used item!",
            "role_id": None,
            "temp_role_id": None,
            "duration": 0,
            "delay": 0,
            "instant_message": None,
            "give_item": normalize_item(give_item) if give_item else None,
            "give_item_amount": give_item_amount,
        }
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Use effect for **{item_name}** saved. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", item_name, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def _apply_use_edit(self, original_key: str, interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_uses", {})
        new_key = normalize_item(item)
        previous = guild["item_uses"].get(original_key) or {}
                                   
        if new_key != original_key and original_key in guild.get("item_uses", {}):
            try:
                del guild["item_uses"][original_key]
            except Exception:
                pass
        guild["item_uses"][new_key] = {
            "money": money,
            "xp": xp,
            "message": message or "Used item!",
            "role_id": None,
            "temp_role_id": None,
            "duration": 0,
            "delay": previous.get("delay", 0),
            "instant_message": previous.get("instant_message"),
            "give_item": normalize_item(give_item) if give_item else None,
            "give_item_amount": give_item_amount,
        }
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Use effect for **{new_key}** updated. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", new_key, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def handle_use_role_selection(self, interaction: discord.Interaction, role_id: int | None, item_name: str, settings_message: discord.Message | None, is_temp_role: bool):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id) if interaction.guild and role_id else None
        if role_id and role is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if is_temp_role:
            effect["temp_role_id"] = role_id
            save_data(data)
            if role_id is None:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:approve:1517452125687513158> Temp role setup skipped for **{item_name}**.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_modal(
                    EconomyTempRoleDurationModal(self.handle_temp_role_duration_submit, self.guild_id, item_name, settings_message)
                )
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
            return

        effect["role_id"] = role_id
        save_data(data)
        if role_id is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Role setup skipped for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Role saved for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def handle_temp_role_duration_submit(self, interaction: discord.Interaction, days: int, hours: int, minutes: int, seconds: int, item_name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        effect["duration"] = max(0, days * 86400 + hours * 3600 + minutes * 60 + seconds)
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Temp role duration saved for **{item_name}**.",
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_use_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("item_uses", {}), item)
        if canonical:
            del guild["item_uses"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed use effect for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No use effect found for **{item}**.", ephemeral=True)

    async def handle_prices_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Item prices?",
            view=EconomyChoiceView(self.user_id, self.open_prices_add, self.open_prices_remove, "prices", self.open_prices_edit, settings_message),
            ephemeral=True,
        )

    async def open_prices_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceSetModal(self.set_price_item, self.guild_id, settings_message))

    async def open_prices_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceRemoveModal(self.remove_price_item, self.guild_id, settings_message))

    async def open_prices_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_price_edit_launch, self.guild_id, "prices", settings_message))

    async def open_price_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
        view = PriceEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Price entry found. Click below to continue editing.", view=view, ephemeral=True)

    async def set_price_item(self, interaction: discord.Interaction, item: str, value: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_values", {})
        guild["item_values"][normalize_item(item)] = value
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Price for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def _apply_price_edit(self, original_key: str, interaction: discord.Interaction, item: str, value: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_values", {})
        new_key = normalize_item(item)
                                   
        if new_key != original_key and original_key in guild.get("item_values", {}):
            try:
                del guild["item_values"][original_key]
            except Exception:
                pass
        guild["item_values"][new_key] = value
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Price for **{new_key}** updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_price_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("item_values", {}), item)
        if canonical:
            del guild["item_values"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed price for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No price found for **{item}**.", ephemeral=True)

    async def handle_crafts_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Crafting recipes?",
            view=EconomyChoiceView(self.user_id, self.open_craft_add, self.open_craft_remove, "crafts", self.open_craft_edit, settings_message),
            ephemeral=True,
        )

    async def open_craft_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftAddModal(self.add_craft_item, self.guild_id, settings_message))

    async def open_craft_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftRemoveModal(self.remove_craft_item, self.guild_id, settings_message))

    async def open_craft_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_craft_edit_launch, self.guild_id, "crafts", settings_message))

    async def open_craft_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
        view = CraftEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Recipe found. Click below to continue editing.", view=view, ephemeral=True)

    async def _apply_craft_edit(self, original_key: str, interaction: discord.Interaction, item: str, requirements: list[tuple[str, int]], delay: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("recipes", {})
        new_key = normalize_item(item)
        recipe = {"reqs": {normalize_item(name): count for name, count in requirements}, "delay": delay}
        if new_key != original_key and original_key in guild.get("recipes", {}):
            try:
                del guild["recipes"][original_key]
            except KeyError:
                pass
        guild["recipes"][new_key] = recipe
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Craft recipe for **{new_key}** updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def add_craft_item(self, interaction: discord.Interaction, item: str, requirements: list[tuple[str, int]], delay: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("recipes", {})
        recipe = {"reqs": {normalize_item(name): count for name, count in requirements}, "delay": delay}
        guild["recipes"][normalize_item(item)] = recipe
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Craft recipe for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_craft_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("recipes", {})
        canonical = find_item_key(guild.get("recipes", {}), item)
        if canonical:
            del guild["recipes"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed craft recipe for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No craft recipe found for **{item}**.", ephemeral=True)




def parse_craft_requirements(value: str) -> list[tuple[str, int]]:
    raw_value = (value or "").strip()
    if not raw_value:
        raise ValueError("At least 1 ingredient is required.")

    parenthesized = [part.strip() for part in re.findall(r"\(([^)]+)\)", raw_value) if part.strip()]
    if parenthesized:
        parts = parenthesized
    else:
        parts = [part.strip() for part in re.split(r"/|\n", raw_value) if part.strip()]

    if len(parts) < 1:
        raise ValueError("At least 1 ingredient is required.")
    if len(parts) > 10:
        raise ValueError("You can set up to 10 ingredients only.")

    requirements: list[tuple[str, int]] = []
    for part in parts:
        name, amount = parse_item_amount_entry(part, default_amount=1)
        if not name:
            raise ValueError("Each ingredient must use the format Item:Amount.")
        requirements.append((name, amount))

    return requirements


def format_recipe_requirements(recipe: dict) -> str:
    reqs = recipe.get("reqs", {}) or {}
    if not reqs:
        return "No ingredients"
    return ", ".join(f"{amount}x {name}" for name, amount in sorted(reqs.items(), key=lambda item: item[0].lower()))


class EconomyTempRoleDurationModal(Modal):
    def __init__(self, callback, guild_id: str, item_name: str, settings_message: discord.Message | None):
        super().__init__(title="Set temp role duration")
        self.callback = callback
        self.guild_id = guild_id
        self.item_name = item_name
        self.settings_message = settings_message
        self.days_input = TextInput(label="Days", placeholder="0", required=True, max_length=10)
        self.hours_input = TextInput(label="Hours", placeholder="0", required=True, max_length=10)
        self.minutes_input = TextInput(label="Minutes", placeholder="0", required=True, max_length=10)
        self.seconds_input = TextInput(label="Seconds", placeholder="0", required=True, max_length=10)
        self.add_item(self.days_input)
        self.add_item(self.hours_input)
        self.add_item(self.minutes_input)
        self.add_item(self.seconds_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days_input.value or 0)
            hours = int(self.hours_input.value or 0)
            minutes = int(self.minutes_input.value or 0)
            seconds = int(self.seconds_input.value or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Days, hours, minutes, and seconds must be numbers.", ephemeral=True)
            return
        await self.callback(interaction, days, hours, minutes, seconds, self.item_name, self.settings_message)


class EconomyShopAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add shop item")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.name_input = TextInput(label="Item name", placeholder="Name of the shop item", required=True, max_length=100)
        self.desc_input = TextInput(label="Description", placeholder="Short description", required=True, max_length=200)
        self.price_input = TextInput(label="Price", placeholder="Item price", required=True, max_length=10)
        self.add_item(self.name_input)
        self.add_item(self.desc_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
            return
        await self.callback(interaction, self.name_input.value.strip(), self.desc_input.value.strip(), price, self.settings_message)


class EconomyShopRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove shop item")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.name_input = TextInput(label="Item name", placeholder="Item to remove", required=True, max_length=100)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.name_input.value.strip(), self.settings_message)


class EconomyUseAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add item use")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item name", required=True, max_length=100)
        self.money_input = TextInput(label="Money reward", placeholder="0", required=True, max_length=10)
        self.xp_input = TextInput(label="XP reward", placeholder="0", required=True, max_length=10)
        self.message_input = TextInput(label="Response message", placeholder="Used item!", required=False, max_length=200)
        self.give_item_input = TextInput(label="Give item (Item:Amount)", placeholder="Optional item:amount", required=False, max_length=100)
        self.add_item(self.item_input)
        self.add_item(self.money_input)
        self.add_item(self.xp_input)
        self.add_item(self.message_input)
        self.add_item(self.give_item_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            money = int(self.money_input.value or 0)
            xp = int(self.xp_input.value or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Money/XP must be numbers.", ephemeral=True)
            return

        give_item, give_amount = parse_item_amount_entry(self.give_item_input.value, default_amount=1)

        await self.callback(interaction, self.item_input.value.strip(), money, xp, self.message_input.value.strip(), give_item, give_amount, self.settings_message)


class EconomyUseRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove item use")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.item_input.value.strip(), self.settings_message)


class EconomyPriceSetModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Set item price")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item name", required=True, max_length=100)
        self.price_input = TextInput(label="Price", placeholder="Sell price", required=True, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.price_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
            return
        await self.callback(interaction, self.item_input.value.strip(), value, self.settings_message)


class EconomyPriceRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove item price")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.item_input.value.strip(), self.settings_message)


class EconomyCraftAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add craft recipe")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Crafted item", placeholder="Result item", required=True, max_length=100)
        self.items_input = TextInput(label="Ingredient list", placeholder="(item:amount)(item:amount)", required=True, max_length=1000)
        self.delay_input = TextInput(label="Delay seconds", placeholder="0", required=True, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.items_input)
        self.add_item(self.delay_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delay_input.value or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Delay must be a number.", ephemeral=True)
            return

        try:
            requirements = parse_craft_requirements(self.items_input.value)
        except ValueError as error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> {error}", ephemeral=True)
            return

        await self.callback(interaction, self.item_input.value.strip(), requirements, delay, self.settings_message)


class EconomyCraftRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove craft recipe")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Crafted item", placeholder="Recipe to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.item_input.value.strip(), self.settings_message)


class EconomyActionModal(Modal):
    def __init__(self, callback, guild_id: str, section: str, settings_message: discord.Message | None = None):
        super().__init__(title="Find entry to edit")
        self.callback = callback
        self.guild_id = guild_id
        self.section = section
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item or name", placeholder="Name or number", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.item_input.value.strip()
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
                                           
        if self.section == "crafts":
            section_key = "recipes"
        elif self.section == "shop":
            section_key = "shop"
        elif self.section == "prices":
            section_key = "item_values"
        elif self.section == "uses":
            section_key = "item_uses"
        else:
            section_key = self.section
        candidates = guild.get(section_key, {})

                             
        canonical = find_item_key(candidates, raw)

                                                                                          
        if canonical is None and raw.isdigit():
            idx = int(raw) - 1
            keys = list(sorted(candidates.keys()))
            if 0 <= idx < len(keys):
                canonical = keys[idx]

                            
        if canonical is None:
            canonical = find_item_key(candidates, normalize_item(raw))

                                                   
        if canonical is None:
            target = raw.lower()
            for k in candidates:
                if target in k.lower():
                    canonical = k
                    break

        if canonical is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Entry not found.", ephemeral=True)
            return

        item_data = candidates.get(canonical)
        await self.callback(interaction, canonical, item_data, self.settings_message)


class ShopEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: dict, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_shop_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_shop_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyShopAddModal(None, self.parent.guild_id, self.settings_message)
        modal.name_input.default = self.canonical
        modal.desc_input.default = self.item_data.get("desc", "")
        modal.price_input.default = str(self.item_data.get("price", 0))

        async def _on_submit(inner_interaction: discord.Interaction, name: str, desc: str, price: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_shop_edit(self.canonical, inner_interaction, name, desc, price, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Shop edit cancelled.", ephemeral=True)


class CraftEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: dict, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_craft_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_craft_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyCraftAddModal(None, self.parent.guild_id, self.settings_message)
        modal.item_input.default = self.canonical
        reqs = self.item_data.get("reqs", {})
        req_items = list(reqs.items())
        modal.items_input.default = "".join(f"({name}:{amount})" for name, amount in req_items)
        modal.delay_input.default = str(self.item_data.get("delay", 0))

        async def _on_submit(inner_interaction: discord.Interaction, item: str, requirements: list[tuple[str, int]], delay: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_craft_edit(self.canonical, inner_interaction, item, requirements, delay, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Craft edit cancelled.", ephemeral=True)


class UseEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: dict, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_use_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_use_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyUseAddModal(None, self.parent.guild_id, self.settings_message)
        modal.item_input.default = self.canonical
        modal.money_input.default = str(self.item_data.get("money", 0))
        modal.xp_input.default = str(self.item_data.get("xp", 0))
        modal.message_input.default = self.item_data.get("message", "")
        give_item = self.item_data.get("give_item")
        if give_item:
            modal.give_item_input.default = f"{give_item}:{self.item_data.get('give_item_amount', 1)}"

        async def _on_submit(inner_interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_use_edit(self.canonical, inner_interaction, item, money, xp, message, give_item, give_item_amount, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Use edit cancelled.", ephemeral=True)


class PriceEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: int | None, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_price_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_price_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyPriceSetModal(None, self.parent.guild_id, self.settings_message)
        modal.item_input.default = self.canonical
        modal.price_input.default = str(self.item_data or 0)

        async def _on_submit(inner_interaction: discord.Interaction, item: str, value: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_price_edit(self.canonical, inner_interaction, item, value, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Price edit cancelled.", ephemeral=True)


# -------------------------------------------------------------------------------------------------------------
#                                               Cog
# -------------------------------------------------------------------------------------------------------------


def _resolve_inventory_item(guild: dict, item: str) -> str:
    canonical_item = find_item_key(guild.get("recipes", {}), item)
    if canonical_item is None:
        canonical_item = find_item_key(guild.get("item_uses", {}), item)
    if canonical_item is None:
        canonical_item = find_item_key(guild.get("item_values", {}), item)
    if canonical_item is None:
        canonical_item = normalize_item(item)
    return canonical_item


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._background_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        # Keep a reference so the task isn't garbage-collected before it finishes.
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    @app_commands.command(name="economy-leaderboard", description="Show the server economy leaderboard")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        if not await ensure_economy_enabled(interaction):
            return
        if limit <= 0:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> Limit must be greater than 0.", ephemeral=True)

        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        users = guild.get("users", {})
        if not users:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("No economy data for this server.", ephemeral=True)

        # Resolving members can take a while (one API call each), so acknowledge first.
        await interaction.response.defer()

        leaderboard = []
        for uid, udata in users.items():
            balance = udata.get("balance", 0)
            leaderboard.append((uid, balance))

        leaderboard.sort(key=lambda x: x[1], reverse=True)
        top = leaderboard[:limit]

        description_lines = []
        for idx, (uid, bal) in enumerate(top, start=1):
            member = interaction.guild.get_member(int(uid))
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(int(uid))
                except Exception:
                    member = None
            name = member.display_name if member else f"User left server (`{uid}`)"
            description_lines.append(f"`#{idx}` **{name}** - ${bal}")

        embed = discord.Embed(title=f"<:chalice:1517579767573123092> Economy Standings Leaderboard - {interaction.guild.name}", color=discord.Color.gold())
        embed.description = "\n".join(description_lines)[:4096]
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="balance", description="Check your balance or another user's balance")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(user="The user whose balance you want to check")
    async def eco_balance(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await ensure_economy_enabled(interaction):
            return
        target = user or interaction.user
        data = load_data()
        money = data.get(str(interaction.guild.id), {}).get("users", {}).get(str(target.id), {}).get("balance", 0)
        await interaction.response.defer(); await interaction.followup.send(f"<:money:1517580310395486239> {target.display_name}'s balance: **${money}**")

    @app_commands.command(name="daily", description="Claim your daily reward")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
    async def eco_daily(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        earnings = random.randint(150, 200)
        user_data["balance"] += earnings
        save_data(data)
        await interaction.response.defer(); await interaction.followup.send(f"<:money:1517580310395486239> You claimed your daily reward and earned **${earnings}**!")

    @app_commands.command(name="pay", description="Pay another user from your balance")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_pay(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not await ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be greater than 0.", ephemeral=True)
        data = load_data()
        guild_id = str(interaction.guild.id)
        sender_data = get_user_data(data, guild_id, str(interaction.user.id))
        receiver_data = get_user_data(data, guild_id, str(user.id))
        if sender_data["balance"] < amount:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You don't have enough money!", ephemeral=True)
        sender_data["balance"] -= amount
        receiver_data["balance"] += amount
        save_data(data)
        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Successfully sent **${amount}** to {format_user_reference(user)}!")

    @app_commands.command(name="shop", description="View the server shop")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_shop(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        shop_items = data.get(str(interaction.guild.id), {}).get("shop", {})
        if not shop_items:
            await interaction.response.defer(); await interaction.followup.send("The shop is currently empty!")
            return

        view = ShopView(shop_items, str(interaction.guild.id), str(interaction.user.id))
        await interaction.response.defer(); await interaction.followup.send(view=view)

    @app_commands.command(name="buy", description="Buy a shop item directly")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(
        item="The shop item to buy",
        amount="How many of the item to buy (up to 99)"
    )
    async def eco_buy(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name="buy")
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(error_message, ephemeral=True)

        data = load_data()
        guild_id = str(interaction.guild.id)
        guild = get_guild_data(data, guild_id)
        user_data = get_user_data(data, guild_id, str(interaction.user.id))

        canonical_item = find_item_key(guild.get("shop", {}), item)
        if canonical_item is None:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> That item is not available in the shop.", ephemeral=True)

        shop_info = guild["shop"][canonical_item]
        price = int(shop_info.get("price", 0))
        total_price = price * amount

        if user_data["balance"] < total_price:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(
                f"<:disapprove:1517452151012589662> You can't afford this purchase. Total cost: **${total_price}**.",
                ephemeral=True,
            )

        user_data["balance"] -= total_price
        inventory_add(user_data["inventory"], canonical_item, amount)
        save_data(data)

        await interaction.response.defer(); await interaction.followup.send(
            f"<:approve:1517452125687513158> You bought **{amount}x {canonical_item}** for **${total_price}**!"
        )

    @app_commands.command(name="inventory", description="Check your inventory or another user's inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(user="The user whose inventory you want to check")
    async def eco_inventory(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await ensure_economy_enabled(interaction):
            return
        target = user or interaction.user
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(target.id))
        inv = user_data.get("inventory", {})
        embed = discord.Embed(title=f"<:box:1517581439552585759> {target.display_name}'s Inventory", color=discord.Color.green())
        if not inv:
            embed.description = "This inventory is currently empty."
        else:
            embed.description = "\n".join(f"• {item} ×{count}" for item, count in inv.items())[:4096]
        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    @app_commands.command(name="inventory-edit", description="Edit a user's inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    async def eco_inventory_edit(self, interaction: discord.Interaction, user: discord.Member, item: str, action: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        item = normalize_item(item)
        action = action.lower().strip()
        if action not in ("add", "remove"):
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> Action must be **add** or **remove**.", ephemeral=True)
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be greater than 0.", ephemeral=True)
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
        if action == "add":
            inventory_add(user_data["inventory"], item, amount)
        else:
            removed = inventory_remove(user_data["inventory"], item, amount)
            if removed < amount:
                save_data(data)
                await interaction.response.defer(ephemeral=True)
                return await interaction.followup.send(
                    f"<:warning:1517452174991556758> Only removed **{removed}x {item}** - {user.display_name} didn't have enough.", ephemeral=True
                )
        save_data(data)
        direction = "to" if action == "add" else "from"
        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> {action.capitalize()}d **{amount}x {item}** {direction} {user.display_name}'s inventory.")

    @app_commands.command(name="balance-edit", description="Set a user's balance")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    async def eco_balance_edit(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
        user_data["balance"] = amount
        save_data(data)
        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Set {user.display_name}'s balance to **${amount}**.")

    @app_commands.command(name="craft", description="Craft an item")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_craft(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name="craft")
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(error_message, ephemeral=True)

        guild_id = str(interaction.guild.id)
        data = load_data()
        guild = get_guild_data(data, guild_id)
        user_data = get_user_data(data, guild_id, str(interaction.user.id))
        canonical_item = find_item_key(guild["recipes"], item)
        if not canonical_item:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> This item is not craftable.", ephemeral=True)
        recipe = guild["recipes"][canonical_item]
        delay = recipe.get("delay", 0)
        requirement_text = format_recipe_requirements(recipe)
        for req_item, count in sorted(recipe["reqs"].items(), key=lambda item: item[0].lower()):
            if inventory_count(user_data["inventory"], req_item) < (count * amount):
                await interaction.response.defer(ephemeral=True)
                return await interaction.followup.send(f"<:disapprove:1517452151012589662> You don't have enough **{req_item}**.", ephemeral=True)
        await interaction.response.defer(); await interaction.followup.send(f"🔨 Starting to craft {amount}x **{canonical_item}**... (Wait {delay}s)\nRequirements: {requirement_text}")
        if delay > 0:
            await asyncio.sleep(delay)

        # Reload: other commands may have changed the file while we were waiting. Saving the
        # copy loaded above would overwrite those changes.
        data = load_data()
        user_data = get_user_data(data, guild_id, str(interaction.user.id))
        for req_item, count in sorted(recipe["reqs"].items(), key=lambda item: item[0].lower()):
            if inventory_count(user_data["inventory"], req_item) < (count * amount):
                return await interaction.followup.send("<:disapprove:1517452151012589662> Crafting failed: You spent your ingredients while waiting!", ephemeral=True)
        for req_item, count in sorted(recipe["reqs"].items(), key=lambda item: item[0].lower()):
            inventory_remove(user_data["inventory"], req_item, count * amount)
        inventory_add(user_data["inventory"], canonical_item, amount)
        save_data(data)

        await interaction.followup.send(f"<:approve:1517452125687513158> Finished crafting {amount}x **{canonical_item}**!")

    @app_commands.command(name="use", description="Use an item from your inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_use(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name="use")
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(error_message, ephemeral=True)

        guild_id = str(interaction.guild.id)
        data = load_data()
        guild = get_guild_data(data, guild_id)
        user_data = get_user_data(data, guild_id, str(interaction.user.id))
        if inventory_count(user_data["inventory"], item) < amount:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(f"<:disapprove:1517452151012589662> You need **{amount}x** of this item to do that.", ephemeral=True)
        canonical_item = find_item_key(guild["item_uses"], item)
        if not canonical_item:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> This item has no special use effect.", ephemeral=True)
        effect = guild["item_uses"][canonical_item]
        if amount > 1 and (effect.get("role_id") or effect.get("temp_role_id")):
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You cannot use role-giving items multiple times at once.", ephemeral=True)
        if effect.get("instant_message"):
            await interaction.response.defer(); await interaction.followup.send(effect["instant_message"])
        else:
            await interaction.response.defer()
        if effect.get("delay", 0) > 0:
            await asyncio.sleep(effect["delay"])

        # Reload after waiting so we don't overwrite changes made in the meantime, and make
        # sure the items weren't sold or given away during the delay.
        data = load_data()
        user_data = get_user_data(data, guild_id, str(interaction.user.id))
        if inventory_count(user_data["inventory"], item) < amount:
            return await interaction.followup.send(f"<:disapprove:1517452151012589662> You need **{amount}x** of this item to do that.", ephemeral=True)

        total_money = 0
        reward_items_given = []
        total_xp = 0
        for _ in range(amount):
            inventory_remove(user_data["inventory"], item)
            total_money += effect.get("money", 0)
            total_xp += effect.get("xp", 0)
            if effect.get("give_item"):
                reward_name = effect["give_item"]
                reward_amount = effect.get("give_item_amount", 1)
                inventory_add(user_data["inventory"], reward_name, reward_amount)
                reward_items_given.append(reward_name)
        user_data["balance"] += total_money
        save_data(data)

        if amount == 1:
            if effect.get("role_id"):
                role = interaction.guild.get_role(effect["role_id"])
                if role and interaction.guild.me.top_role > role:
                    try:
                        await interaction.user.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(interaction.guild.id, interaction.channel_id, interaction.user, "item use role grant", error)
            if effect.get("temp_role_id"):
                role = interaction.guild.get_role(effect["temp_role_id"])
                if role and interaction.guild.me.top_role > role:
                    try:
                        await interaction.user.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(interaction.guild.id, interaction.channel_id, interaction.user, "item use temp role grant", error)
                    else:
                        async def remove_role(r, duration):
                            await asyncio.sleep(duration)
                            try:
                                await interaction.user.remove_roles(r)
                            except discord.Forbidden as error:
                                add_bot_error_entry(interaction.guild.id, interaction.channel_id, interaction.user, "item use temp role remove", error)
                        self._spawn(remove_role(role, effect.get("duration", 0)))

        if total_xp > 0:
            levels_cog = self.bot.get_cog('LevelsCog')
            if levels_cog is not None:
                await levels_cog.add_xp(interaction.user, interaction.guild, total_xp, announce_channel=interaction.channel)
        final_msg = f"<:spark:1517583248421552305> [{amount}x] {effect.get('message', 'Used item!')}"
        if total_money > 0:
            final_msg += f" (Reward: ${total_money})"
        if total_xp > 0:
            final_msg += f" (+{total_xp} XP)"
        if reward_items_given:
            final_msg += f" (Received: {reward_items_given[0]}!)"
        await interaction.followup.send(final_msg)

    @app_commands.command(name="sell", description="Sell a specific amount of an item from your inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_sell(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name="sell")
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(error_message, ephemeral=True)

        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        canonical_item = find_item_key(guild.get("item_values", {}), item)
        if canonical_item is None:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(f"<:disapprove:1517452151012589662> **{item}** cannot be sold. No price has been set for it.", ephemeral=True)
        item_price = guild["item_values"][canonical_item]
        user_count = inventory_count(user_data["inventory"], canonical_item)
        if user_count < amount:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(
                f"<:disapprove:1517452151012589662> You don't have enough! You have **{user_count}x {canonical_item}**, but tried to sell **{amount}x**.", ephemeral=True
            )
        inventory_remove(user_data["inventory"], canonical_item, amount)
        total_value = item_price * amount
        user_data["balance"] += total_value
        save_data(data)
        await interaction.response.defer(); await interaction.followup.send(
            f"<:money:1517580310395486239> You sold **{amount}x {canonical_item}** for a total of **${total_value}**!\n"
            f"Your new balance is **${user_data['balance']}**."
        )

    @app_commands.command(name="trash", description="Delete an item from your inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_trash(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name="delete")
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(error_message, ephemeral=True)

        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        canonical_item = _resolve_inventory_item(guild, item)

        user_count = inventory_count(user_data["inventory"], canonical_item)
        if user_count < amount:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(
                f"<:disapprove:1517452151012589662> You don't have enough! You have **{user_count}x {canonical_item}**, but tried to delete **{amount}x**.",
                ephemeral=True,
            )

        inventory_remove(user_data["inventory"], canonical_item, amount)
        save_data(data)
        await interaction.response.defer(); await interaction.followup.send(
            f"<:trash:1517497581058527404> Deleted **{amount}x {canonical_item}** from your inventory."
        )

    @app_commands.command(name="give", description="Give an item from your inventory to another user")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_give(self, interaction: discord.Interaction, user: discord.Member, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name="give")
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(error_message, ephemeral=True)

        if user.id == interaction.user.id:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You can't give an item to yourself.", ephemeral=True)

        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        sender_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        receiver_data = get_user_data(data, str(interaction.guild.id), str(user.id))
        canonical_item = _resolve_inventory_item(guild, item)

        sender_count = inventory_count(sender_data["inventory"], canonical_item)
        if sender_count < amount:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(
                f"<:disapprove:1517452151012589662> You don't have enough! You have **{sender_count}x {canonical_item}**, but tried to give **{amount}x**.",
                ephemeral=True,
            )

        inventory_remove(sender_data["inventory"], canonical_item, amount)
        inventory_add(receiver_data["inventory"], canonical_item, amount)
        save_data(data)
        await interaction.response.defer(); await interaction.followup.send(
            f"<:approve:1517452125687513158> Gave **{amount}x {canonical_item}** to {format_user_reference(user)}."
        )

    @app_commands.command(name="trade", description="Start a trade with another user")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_trade(self, interaction: discord.Interaction, user: discord.Member):
        if not await ensure_economy_enabled(interaction):
            return
        if user.id == interaction.user.id:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You can't trade with yourself.", ephemeral=True)
        if user.bot:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> You can't trade with bots.", ephemeral=True)

        view = TradeView(interaction.user, user)
        await interaction.response.defer(); await interaction.followup.send(view=view)
        view.trade_message = await interaction.original_response()

    @app_commands.command(name="values_info", description="Show all items that can be sold and their prices")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def values_info(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        prices = guild.get("item_values", {})
        if not prices:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> No items have a selling price set yet.", ephemeral=True)

        embed = discord.Embed(title="<:money:1517580310395486239> Item Market Prices", color=discord.Color.gold())
        for item, price in list(prices.items())[:25]:
            embed.add_field(name=item, value=f"Sell Price: **${price}**", inline=False)
        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    @app_commands.command(name="recipes_info", description="Show all available crafting recipes")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def recipes_info(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        recipes = guild.get("recipes", {})
        if not recipes:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> No crafting recipes found.", ephemeral=True)

        embed = discord.Embed(title="<:craft:1518348021161660539> Crafting Book", color=discord.Color.blue())
        for result_item, recipe in sorted(recipes.items(), key=lambda item: item[0].lower())[:25]:
            ing_list = format_recipe_requirements(recipe)
            delay_str = f"<:timer:1517996239583576194> {recipe.get('delay', 0)}s" if recipe.get("delay", 0) > 0 else ""
            embed.add_field(
                name=result_item,
                value=(f"Requires: {ing_list}" + (f"\n{delay_str}" if delay_str else ""))[:1024],
                inline=False,
            )
        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    @app_commands.command(name="uses_info", description="Show what items do when used")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def uses_info(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        uses = guild.get("item_uses", {})
        if not uses:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

        embed = discord.Embed(title="<:Vial:1517681553377857628> Item Effects Directory", color=discord.Color.green())
        for item, effect in uses.items():
            if len(embed.fields) >= 25:
                break
            details = []
            money = effect.get("money", 0)
            if money > 0:
                details.append(f"<:money:1517580310395486239> Gives Money: **${money}**")
            xp_amount = effect.get("xp", 0)
            if xp_amount > 0:
                details.append(f"<:Vial:1517681553377857628> Grants XP: **{xp_amount} XP**")
            give_item = effect.get("give_item")
            if give_item:
                amt = effect.get("give_item_amount", 1)
                details.append(f"<:box:1517581439552585759> Gives: **{amt}x {give_item}**")
            if effect.get("role_id"):
                role = interaction.guild.get_role(effect["role_id"])
                if role:
                    details.append(f"<:shield:1518340640801427566> Grants Role: **{role.name}**")
            if effect.get("temp_role_id"):
                role = interaction.guild.get_role(effect["temp_role_id"])
                dur = effect.get("duration", 0)
                if role:
                    details.append(f"<:hourglass:1517574046252924938> Temp Role: **{role.name}** ({dur}s)")
            delay = effect.get("delay", 0)
            if delay > 0:
                details.append(f"<:timer:1517996239583576194> Delay: {delay}s")
            msg = effect.get("message")
            if msg and msg != "Used item!":
                details.append(f"<:list:1517497572770451567> Message: *{msg}*")
            if details:
                embed.add_field(name=item, value="\n".join(details)[:1024], inline=False)

        if not embed.fields:
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send("<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

        await interaction.response.defer(); await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
