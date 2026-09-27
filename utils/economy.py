"""Shared economy helpers: wallets, inventories and item-amount parsing.

Used by the economy and games cogs, level rewards and giveaways. Reading and writing
economy.json itself is in save.py (load_data / save_data).
"""

import discord

import save

MAX_ITEM_BATCH_SIZE = 99


def get_guild_data(data, guild_id):
    if guild_id not in data:
        data[guild_id] = {
            "users": {},
            "shop": {},
            "recipes": {},
            "item_uses": {},
            "item_values": {}
        }
    return data[guild_id]


def migrate_inventory(user: dict) -> None:
    inv = user.get("inventory")
    if isinstance(inv, list):
        stacked: dict = {}
        for item in inv:
            stacked[item] = stacked.get(item, 0) + 1
        user["inventory"] = stacked


def get_user_data(data, guild_id, user_id):
    guild = get_guild_data(data, guild_id)
    user_id = str(user_id)
    if user_id not in guild["users"]:
        guild["users"][user_id] = {"balance": 0, "inventory": {}}
    migrate_inventory(guild["users"][user_id])
    return guild["users"][user_id]


def normalize_item(name: str) -> str:
    return name.strip().title()


def find_item_key(dictionary: dict, item_name: str) -> str | None:
    target = item_name.strip().lower()
    for key in dictionary:
        if key.lower() == target:
            return key
    return None


def inventory_count(inventory: dict, item_name: str) -> int:
    key = find_item_key(inventory, item_name)
    return inventory[key] if key else 0


def inventory_add(inventory: dict, item_name: str, amount: int = 1) -> None:
    key = find_item_key(inventory, item_name)
    if key:
        inventory[key] += amount
    else:
        inventory[item_name] = amount


def inventory_remove(inventory: dict, item_name: str, amount: int = 1) -> int:
    key = find_item_key(inventory, item_name)
    if not key:
        return 0
    available = inventory[key]
    removed = min(available, amount)
    if removed >= available:
        del inventory[key]
    else:
        inventory[key] -= removed
    return removed


def validate_item_batch_amount(amount: int, *, action_name: str) -> tuple[bool, str | None]:
    if amount <= 0:
        return False, f"<:disapprove:1517452151012589662> You must {action_name} at least 1 item."
    if amount > MAX_ITEM_BATCH_SIZE:
        return False, f"<:disapprove:1517452151012589662> You can only {action_name} up to {MAX_ITEM_BATCH_SIZE} items at once."
    return True, None


def parse_item_amount_entry(value: str, default_amount: int = 1):
    text = (value or "").strip()
    if not text:
        return None, default_amount
    if ":" in text:
        name, amount_text = text.rsplit(":", 1)
        try:
            amount = int(amount_text.strip() or default_amount)
        except ValueError:
            amount = default_amount
        return (name.strip() or None), amount
    return text, default_amount


async def ensure_economy_enabled(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return True
    if not save.is_economy_enabled(str(interaction.guild.id)):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Economy features are disabled in this server.", ephemeral=True)
        return False
    return True
