import os
import sys
import time
import subprocess
from pathlib import Path


def _child_cmd():
    main_py = Path(__file__).with_name("main.py")
    return [sys.executable, str(main_py)]


def run_forever():
    while True:
        try:
            cmd = _child_cmd()
            env = os.environ.copy()
            ret = subprocess.call(cmd, env=env)
            if ret == 0:
                print("[Supervisor] App exited normally. Stop.")
                break
            print("[Supervisor] App crashed. Restart after 5s.")
            time.sleep(5)
        except Exception as e:
            print(f"[Supervisor] Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_forever()
