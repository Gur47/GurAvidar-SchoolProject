import threading
import subprocess
import time
import os

def run_client(index):
    # 1. יצירת קובץ credentials זמני לכל לקוח
    filename = f"creds_{index}.txt"
    username = f"user_{index}"  # וודא שהמשתמשים האלו קיימים ב-DB
    password = "123"
    
    with open(filename, "w") as f:
        f.write(f"{username}|{password}")
    
    # 2. הרצת הלקוח כ-Subprocess שקורא את הקובץ
    # אנחנו משתמשים ב-sys.executable כדי להשתמש באותו פייתון שבו רץ הסקריפט
    import sys
    subprocess.run([sys.executable, "client.py", filename])

    if os.path.exists(filename):
        os.remove(filename)
def main():
    threads = []
    print("Starting 20 clients...")
    
    for i in range(1, 21):
        # יצירת Thread לכל לקוח
        t = threading.Thread(target=run_client, args=(i,))
        threads.append(t)
        t.start()
        time.sleep(0.2) # השהייה קטנה כדי לא לחנוק את השרת בבת אחת
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()