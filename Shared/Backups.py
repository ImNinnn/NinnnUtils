import zipfile
from datetime import datetime
from pathlib import Path

from main import BASE_DIR


def get_backup_dir() -> Path:
    return Path(BASE_DIR) / 'backups'


def get_backup_files() -> list[Path]:
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []
    return sorted([p for p in backup_dir.iterdir() if p.is_file() and p.suffix == '.zip'], key=lambda p: p.name, reverse=True)


def format_backup_entry(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    size = path.stat().st_size
    return f"{path.name} · {size} bytes · {modified}"

def create_backup(root_dir: str = BASE_DIR, backup_folder_name: str = 'backups') -> Path:
    root = Path(root_dir)
    backup_dir = root / backup_folder_name
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    now = datetime.now()
    name = now.strftime("%y.%m.%d.h%H.%M")
    zip_path = backup_dir / f"{name}.zip"

    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p in root.rglob('*.json'):
                if p.is_file():
                    try:
                        arcname = p.relative_to(root).as_posix()
                    except Exception:
                        arcname = p.name
                    zf.write(p, arcname)
        print(f"Created JSON backup: {zip_path}")
    except Exception as e:
        print(f"Failed to create backup {zip_path}: {e}")

    return zip_path

