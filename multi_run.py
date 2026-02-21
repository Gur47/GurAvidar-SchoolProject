# multi_run.py
"""
Spawns 20 simultaneous client threads.

Each thread runs client.py as a subprocess with NO command-line arguments.
The client itself picks a random credentials file from the 10 pre-existing
static files (creds_1.txt … creds_10.txt).

Pre-existing credential files must already exist in the project directory —
this script never creates or deletes them.
"""

import threading
import subprocess
import sys
import time


NUM_CLIENTS = 20


def run_client(index: int):
    """Launch a single client process (no arguments)."""
    print(f"[Thread {index:02d}] Starting client...")
    try:
        result = subprocess.run(
            [sys.executable, "client.py"],
            capture_output=True,
            text=True,
            timeout=30          # safety timeout per client
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            for line in stdout.splitlines():
                print(f"[Thread {index:02d}] {line}")
        if stderr:
            for line in stderr.splitlines():
                print(f"[Thread {index:02d}] STDERR: {line}")

    except subprocess.TimeoutExpired:
        print(f"[Thread {index:02d}] Timed out after 30 s.")
    except Exception as e:
        print(f"[Thread {index:02d}] Error: {type(e).__name__} — {e}")

    print(f"[Thread {index:02d}] Done.")


def main():
    print(f"Launching {NUM_CLIENTS} simultaneous client threads...")
    threads = []

    for i in range(1, NUM_CLIENTS + 1):
        t = threading.Thread(target=run_client, args=(i,), daemon=False)
        threads.append(t)

    # Start all threads as close to simultaneously as possible
    for t in threads:
        t.start()

    # Wait for all to finish
    for t in threads:
        t.join()

    print("All client threads completed.")


if __name__ == "__main__":
    main()