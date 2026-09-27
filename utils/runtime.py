"""Process-wide runtime state: the running bot, the command prefix and the start time.

bot.py assigns `bot` at startup; everything else reads it from here.
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()

PREFIX = os.getenv('PREFIX', '!')
STARTED_AT = time.monotonic()
bot = None

# Kept when this module is reloaded by the cog manager.
_KEEP_ON_RELOAD = ("bot", "STARTED_AT")
