import json
import os

from DataManager import *
from main import FUN_FILE


def load_fun_data():
    return DataManager.load(FUN_FILE, {})

def save_fun_data(data):
    DataManager.save(FUN_FILE, data)