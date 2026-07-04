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
