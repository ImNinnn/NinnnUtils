def load_love_data():
    if not os.path.exists(RATE_FILE):
        save_json_file(RATE_FILE, {})
        return {}
    return load_json_file(RATE_FILE, {})


def save_love_data(data):
    save_json_file(RATE_FILE, data)
