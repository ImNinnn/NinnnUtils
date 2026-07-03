def load_board_data():
    return load_json_file(BOARD_FILE, {})


def save_board_data(data):
    save_json_file(BOARD_FILE, data)

def get_guild_board_entries(guild_id: str) -> list[str]:
    board_data = load_board_data()
    entries = []
    if guild_id in board_data:
        for emoji_key, cfg in board_data[guild_id].items():
            ch_id = cfg.get("channel_id")
            required = cfg.get("required_count")
            channel_repr = f"<#{ch_id}>" if ch_id else "Unknown"
            req_text = f"required {required}" if required is not None else "required ?"
            entries.append(f"{emoji_key} in {channel_repr} ({req_text})")
    return entries

def ensure_board_guild_config(guild_id: str):
    board_data = load_board_data()
    if guild_id not in board_data:
        board_data[guild_id] = {}
    return board_data

