import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

from discord.ext.commands import Cog

from main import BASE_DIR


async def setup(bot):
    await bot.add_cog(Backups(bot))

class Backups(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.start_backup_scheduler()

    def create_backup(self, root_dir: str = BASE_DIR, backup_folder_name: str = 'backups') -> Path:
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

    def _backup_worker(self, interval_seconds: int = 3600, root_dir: str = BASE_DIR):
        while True:
            time.sleep(interval_seconds)
            try:
                self.create_backup(root_dir)
            except Exception as e:
                print(f"Backup error: {e}")

    def start_backup_scheduler(self, interval_seconds: int = 3600, root_dir: str = BASE_DIR):
        try:
            self.create_backup(root_dir)
        except Exception as e:
            print(f"Initial backup failed: {e}")

        t = threading.Thread(target=self._backup_worker, args=(interval_seconds, root_dir), daemon=True)
        t.start()
        return t
