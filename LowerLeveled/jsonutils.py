import os, json
from json.decoder import JSONDecodeError

def load_json_file(path: str, default=None, recover_backup: bool = True):
    if default is None:
        default = {}

    if not os.path.exists(path):
        return default

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except JSONDecodeError:
        if recover_backup:
            backup_path = path + '.bak'
            if os.path.exists(backup_path):
                try:
                    with open(backup_path, 'r', encoding='utf-8') as backup_file:
                        recovered = json.load(backup_file)
                    save_json_file(path, recovered)
                    print(f"Recovered {os.path.basename(path)} from backup after corruption.")
                    return recovered
                except (JSONDecodeError, OSError):
                    pass
        print(f"Warning: {os.path.basename(path)} is corrupted and could not be loaded. Returning default.")
        return default
    except OSError:
        print(f"Warning: unable to read {os.path.basename(path)}. Returning default.")
        return default


def save_json_file(path: str, data, indent: int = 4):
    temp_path = path + '.tmp'
    backup_path = path + '.bak'

    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())

        if os.path.exists(path):
            try:
                os.replace(path, backup_path)
            except OSError:
                pass

        os.replace(temp_path, path)
    except OSError as e:
        print(f"Warning: unable to save {os.path.basename(path)}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass