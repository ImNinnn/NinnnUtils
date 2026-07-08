import os

from LowerLeveled.jsonutils import save_json_file, load_json_file
from main import RATE_FILE


def load_love_data():
    if not os.path.exists(RATE_FILE):
        save_json_file(RATE_FILE, {})
        return {}
    return load_json_file(RATE_FILE, {})


def save_love_data(data):
    save_json_file(RATE_FILE, data)
