# I got lazy
from . import *

class EconomyChoiceView(discord.ui.View):
    def __init__(self, user_id: int, on_add, on_remove, setting_name: str, settings_message: discord.Message | None = None):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.setting_name = setting_name
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id=f"economy_add_{setting_name}")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id=f"economy_remove_{setting_name}")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id=f"economy_cancel_{setting_name}")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)

class EconomyRoleSelectionView(discord.ui.View):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, item_name: str, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        role_id = int(self.role_select.values[0])
        await self.callback(interaction, role_id, self.item_name, self.settings_message, self.is_temp_role)

    async def on_no_selected(self, interaction: discord.Interaction):
        await self.callback(interaction, None, self.item_name, self.settings_message, self.is_temp_role)


class EconomySettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
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
        await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

    async def handle_shop_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Shop items?",
            view=EconomyChoiceView(self.user_id, self.open_shop_add, self.open_shop_remove, "shop", settings_message),
            ephemeral=True,
        )

    async def open_shop_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopAddModal(self.add_shop_item, self.guild_id, settings_message))

    async def open_shop_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopRemoveModal(self.remove_shop_item, self.guild_id, settings_message))

    async def add_shop_item(self, interaction: discord.Interaction, name: str, desc: str, price: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild["shop"][normalize_item(name)] = {"desc": desc, "price": price}
        save_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Shop item **{normalize_item(name)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_shop_item(self, interaction: discord.Interaction, name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("shop", {}), name)
        if canonical:
            del guild["shop"][canonical]
            save_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed shop item **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No shop item found for **{name}**.", ephemeral=True)

    async def handle_uses_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Item uses?",
            view=EconomyChoiceView(self.user_id, self.open_uses_add, self.open_uses_remove, "uses", settings_message),
            ephemeral=True,
        )

    async def open_uses_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseAddModal(self.add_use_item, self.guild_id, settings_message))

    async def open_uses_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseRemoveModal(self.remove_use_item, self.guild_id, settings_message))

    async def add_use_item(self, interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message: discord.Message | None):
        item_name = normalize_item(item)
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
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
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Use effect for **{item_name}** saved. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", item_name, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )

    async def handle_use_role_selection(self, interaction: discord.Interaction, role_id: int | None, item_name: str, settings_message: discord.Message | None, is_temp_role: bool):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id) if interaction.guild and role_id else None
        if role_id and role is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.send_message(role_error, ephemeral=True)
            return

        if is_temp_role:
            effect["temp_role_id"] = role_id
            save_data(data)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
            if role_id is None:
                await interaction.response.send_message(
                    f"<:approve:1517452125687513158> Temp role setup skipped for **{item_name}**.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_modal(
                    EconomyTempRoleDurationModal(self.handle_temp_role_duration_submit, self.guild_id, item_name, settings_message)
                )
            return

        effect["role_id"] = role_id
        save_data(data)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        if role_id is None:
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Role setup skipped for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Role saved for **{item_name}**. Choose a temporary role next, or press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
            ephemeral=True,
        )

    async def handle_temp_role_duration_submit(self, interaction: discord.Interaction, days: int, hours: int, minutes: int, seconds: int, item_name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        effect["duration"] = max(0, days * 86400 + hours * 3600 + minutes * 60 + seconds)
        save_data(data)
        await interaction.response.send_message(
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
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed use effect for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No use effect found for **{item}**.", ephemeral=True)

    async def handle_prices_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Item prices?",
            view=EconomyChoiceView(self.user_id, self.open_prices_add, self.open_prices_remove, "prices", settings_message),
            ephemeral=True,
        )

    async def open_prices_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceSetModal(self.set_price_item, self.guild_id, settings_message))

    async def open_prices_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceRemoveModal(self.remove_price_item, self.guild_id, settings_message))

    async def set_price_item(self, interaction: discord.Interaction, item: str, value: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild["item_values"][normalize_item(item)] = value
        save_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Price for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_price_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("item_values", {}), item)
        if canonical:
            del guild["item_values"][canonical]
            save_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed price for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No price found for **{item}**.", ephemeral=True)

    async def handle_crafts_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Crafting recipes?",
            view=EconomyChoiceView(self.user_id, self.open_craft_add, self.open_craft_remove, "crafts", settings_message),
            ephemeral=True,
        )

    async def open_craft_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftAddModal(self.add_craft_item, self.guild_id, settings_message))

    async def open_craft_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftRemoveModal(self.remove_craft_item, self.guild_id, settings_message))

    async def add_craft_item(self, interaction: discord.Interaction, item: str, req1_name: str, req1_count: int, req2_name: str | None, req2_count: int, delay: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        recipe = {"reqs": {normalize_item(req1_name): req1_count}, "delay": delay}
        if req2_name:
            recipe["reqs"][normalize_item(req2_name)] = req2_count
        guild["recipes"][normalize_item(item)] = recipe
        save_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Craft recipe for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_craft_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("recipes", {}), item)
        if canonical:
            del guild["recipes"][canonical]
            save_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed craft recipe for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No craft recipe found for **{item}**.", ephemeral=True)

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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Days, hours, minutes, and seconds must be numbers.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Money/XP must be numbers.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
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
        self.req1_input = TextInput(label="Requirement 1 (Item:Amount)", placeholder="Ingredient:amount", required=True, max_length=100)
        self.req2_input = TextInput(label="Requirement 2 (Item:Amount)", placeholder="Optional ingredient:amount", required=False, max_length=100)
        self.delay_input = TextInput(label="Delay seconds", placeholder="0", required=True, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.req1_input)
        self.add_item(self.req2_input)
        self.add_item(self.delay_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delay_input.value or 0)
        except ValueError:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Delay must be a number.", ephemeral=True)
            return

        req1_name, req1_count = parse_item_amount_entry(self.req1_input.value, default_amount=1)
        req2_name, req2_count = (None, 1)
        if self.req2_input.value.strip():
            req2_name, req2_count = parse_item_amount_entry(self.req2_input.value, default_amount=1)

        await self.callback(interaction, self.item_input.value.strip(), req1_name, req1_count, req2_name, req2_count, delay, self.settings_message)


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
