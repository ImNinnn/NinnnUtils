from Shared.DataManager import DataManager
from main import DATA_FILE


def load_data():
    return DataManager.load(DATA_FILE, {})



def save_data(data):
    DataManager.save(DATA_FILE, data)
