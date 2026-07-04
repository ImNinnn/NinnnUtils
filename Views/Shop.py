class ShopView(discord.ui.LayoutView):
    def __init__(self, shop_items, guild_id, user_id):
        super().__init__(timeout=180)
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
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="shop_close")

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

        async def close_callback(interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)

        prev_button.callback = prev_callback
        next_button.callback = next_callback
        close_button.callback = close_callback
        self.add_item(discord.ui.ActionRow(prev_button, next_button, close_button))
