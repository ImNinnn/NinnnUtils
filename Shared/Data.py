from LowerLeveled.jsonutils import load_json_file, save_json_file
from main import DATA_FILE


def load_data():
    return load_json_file(DATA_FILE, {})


def save_data(data):
    save_json_file(DATA_FILE, data)
