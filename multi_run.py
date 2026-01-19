import threading
import subprocess
import time
import os
import sys

def run_client(index, action, username, password):
    """
    index: מספר הלקוח
    action: פעולה (LOGIN או REGISTER)
    username/password: פרטי גישה
    """
    filename = f"creds_{index}.txt"
    
    # יצירת הקובץ בפורמט שהמורה ביקש: Action|User|Pass
    with open(filename, "w") as f:
        f.write(f"{action}|{username}|{password}")
    
    print(f"[Client {index}] Attempting {action} for {username}...")
    
    # הרצה
    subprocess.run([sys.executable, "client.py", filename])

    # ניקוי
    if os.path.exists(filename):
        os.remove(filename)

def main():
    threads = []
    
    # הגדרת התרחישים (סה"כ 10 לקוחות)
    scenarios = []
    
    # 6 לקוחות: לוגין מוצלח (קיימים ב-SQL עם סיסמה "123")
    for i in range(1, 7):
        scenarios.append(("LOGIN", f"test_user_{i}", "123"))
        
    # 2 לקוחות: לוגין נכשל (משתמש קיים ב-SQL אבל סיסמה שגויה)
    scenarios.append(("LOGIN", "test_user_1", "wrong_password"))
    scenarios.append(("LOGIN", "test_user_2", "111111"))
    
    # 2 לקוחות: רישום חדש (לא קיימים ב-SQL)
    scenarios.append(("REGISTER", "new_bot_9", "pass9"))
    scenarios.append(("REGISTER", "new_bot_10", "pass10"))

    print(f"Starting POC with {len(scenarios)} diverse clients...")

    for i, (action, user, pwd) in enumerate(scenarios):
        t = threading.Thread(target=run_client, args=(i+1, action, user, pwd))
        threads.append(t)
        t.start()
        time.sleep(0.3)

    for t in threads:
        t.join()

if __name__ == "__main__":
    main()