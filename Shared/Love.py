import os

from LowerLeveled.jsonutils import save_json_file, load_json_file
from Shared.DataManager import DataManager
from main import RATE_FILE


def load_love_data():
    return DataManager.load(RATE_FILE, {})


def save_love_data(data):
    DataManager.save(RATE_FILE, data)
