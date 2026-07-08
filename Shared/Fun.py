import json
import os

from main import FUN_FILE


def load_fun_data():
    if not os.path.exists(FUN_FILE):
        return {}
    with open(FUN_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_fun_data(data):
    with open(FUN_FILE, 'w') as f:
        json.dump(data, f, indent=4)
