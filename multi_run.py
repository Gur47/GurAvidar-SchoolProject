# multi_run.py
"""
מריץ 20 לקוחות בו-זמנית כדי להדגים הגנת DDoS.
הסקריפט יוצר קבצי creds זמניים, מריץ את הלקוחות headless, ומנקה אחרי.
"""

import threading
import subprocess
import sys
import time
import os

NUM_CLIENTS = 20
STAGGER_MS  = 100
HERE = os.path.dirname(os.path.abspath(__file__))

# שנה את הפרטים כך שיתאימו למשתמשים הרשומים ב-DB שלך
DEMO_CREDENTIALS = [
    "LOGIN|test_user_1|123",
    "LOGIN|test_user_2|123",
    "LOGIN|test_user_3|123",
    "LOGIN|test_user_1|123",   # ← חיבור 4 מאותו IP — מפעיל DDoS!
    "LOGIN|test_user_2|123",
    "LOGIN|test_user_3|123",
    "LOGIN|test_user_1|123",
    "LOGIN|test_user_2|123",
    "LOGIN|test_user_3|123",
    "LOGIN|test_user_1|123",
    "LOGIN|test_user_2|123",
    "LOGIN|test_user_3|123",
    "LOGIN|test_user_1|123",
    "LOGIN|test_user_2|123",
    "LOGIN|test_user_3|123",
    "LOGIN|test_user_1|123",
    "LOGIN|test_user_2|123",
    "LOGIN|test_user_3|123",
    "LOGIN|test_user_1|123",
    "LOGIN|test_user_2|123",
]


def create_temp_creds():
    created = []
    for i, line in enumerate(DEMO_CREDENTIALS, start=1):
        path = os.path.join(HERE, f"creds_{i}.txt")
        with open(path, "w") as f:
            f.write(line)
        created.append(path)
    print(f"  [Setup] Created {len(created)} temporary creds files.")
    return created


def delete_temp_creds(paths):
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass
    print(f"  [Cleanup] Removed {len(paths)} temp creds files.")


def run_client(index: int):
    print(f"[Client {index:02d}] ▶  Connecting...")
    try:
        result = subprocess.run(
            [sys.executable, "client.py"],
            capture_output=True,
            text=True,
            timeout=25,
            cwd=HERE
        )
        for line in result.stdout.strip().splitlines():
            print(f"[Client {index:02d}] {line}")
        for line in result.stderr.strip().splitlines():
            if "UserWarning" in line or "warnings.warn" in line:
                continue
            print(f"[Client {index:02d}] ERR: {line}")
    except subprocess.TimeoutExpired:
        print(f"[Client {index:02d}] ⏱  Timed out (connection likely dropped by DDoS).")
    except Exception as e:
        print(f"[Client {index:02d}] ❌ {type(e).__name__}: {e}")
    print(f"[Client {index:02d}] ■  Done.")


def main():
    print("=" * 60)
    print("   MULTI-CLIENT DDoS DEMONSTRATION")
    print("=" * 60)
    print(f"  מפעיל {NUM_CLIENTS} לקוחות במקביל מ-127.0.0.1")
    print(f"  MAX_CONNECTIONS_PER_IP = 3  |  MAX_TOTAL = 15")
    print()
    print("  מה צפוי לקרות:")
    print("  OK  לקוחות 1-3  → יתחברו בהצלחה")
    print("  !!! לקוח 4      → מפעיל DDoS: כל החיבורים מ-127.0.0.1")
    print("                     יינתקו, המשתמשים יסומנו ddos_status=true")
    print("  XXX לקוחות 5+   → יידחו (IP/משתמש חסום)")
    print()
    print("  --> צפה ב-SERVER DASHBOARD בזמן אמת!")
    print("=" * 60)

    temp_files = create_temp_creds()
    print()

    threads = []
    for i in range(1, NUM_CLIENTS + 1):
        t = threading.Thread(target=run_client, args=(i,), daemon=False)
        threads.append(t)

    start_time = time.perf_counter()
    for t in threads:
        t.start()
        time.sleep(STAGGER_MS / 1000)
    for t in threads:
        t.join()

    elapsed = time.perf_counter() - start_time

    print()
    delete_temp_creds(temp_files)
    print()
    print("=" * 60)
    print(f"  סיום: כל {NUM_CLIENTS} לקוחות הסתיימו תוך {elapsed:.1f}s")
    print("  בדוק ב-SERVER DASHBOARD:")
    print("    DDOS EVENTS > 0  |  הודעות !!! ב-EVENT LOG")
    print("=" * 60)


if __name__ == "__main__":
    main()