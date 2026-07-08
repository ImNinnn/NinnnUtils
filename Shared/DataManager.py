from LowerLeveled.jsonutils import load_json_file, save_json_file


class DataManager:
    """Unified data loading and saving for all JSON files"""
    _cache = {}

    @classmethod
    def load(cls, file_path: str, default=None):
        """Load data from JSON file with optional caching"""
        if default is None:
            default = {}
        return load_json_file(file_path, default)

    @classmethod
    def save(cls, file_path: str, data):
        """Save data to JSON file"""
        save_json_file(file_path, data)