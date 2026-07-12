import os
import subprocess
import sys
import time

if len(sys.argv) > 1:
    target_script = os.path.abspath(sys.argv[1])
else:
    target_script = os.path.abspath("main.py")

for _ in range(2):
    time.sleep(5)
    if os.path.exists(target_script):
        subprocess.Popen([sys.executable, target_script], cwd=os.path.dirname(target_script))
        break