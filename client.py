# client.py
import socket
import tkinter as tk
from tkinter import messagebox
import threading
import time
import io
import base64
import os
import random
from PIL import Image, ImageTk
import pyautogui
from encrypt import Encryption
from constants import IP, PORT
from pynput import keyboard
from tkinter import scrolledtext

# ──────────────────────────────────────────────────────────────────────────────
# Pre-defined credential files (10 static files, never created/deleted here)
# Format inside each file: ACTION|username|password  (e.g. LOGIN|alice|pass123)
# ──────────────────────────────────────────────────────────────────────────────
CREDS_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_FILES = [os.path.join(CREDS_DIR, f"creds_{i}.txt") for i in range(1, 11)]


def pick_credentials():
    """
    Randomly select one of the 10 pre-existing credential files.
    Returns (action, username, password, role) if a valid file is found, else None.
    File format: ACTION|username|password  OR  ACTION|username|password|role
    Role defaults to 'parent' if not specified.
    """
    candidates = list(CREDS_FILES)
    random.shuffle(candidates)

    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = f.read().strip().split("|")
                if len(data) >= 3:
                    action = data[0].upper()
                    user = data[1]
                    pwd = data[2]
                    role = data[3] if len(data) >= 4 else "parent"
                    if action in ("LOGIN", "REGISTER"):
                        return action, user, pwd, role
            except Exception:
                pass

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Network layer
# ──────────────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.encryptor = Encryption()
        self.connected = False

    def connect(self):
        try:
            self.sock.connect((IP, PORT))
            self.connected = True
            return True
        except Exception as e:
            return False   # caller decides how to surface the error

    def send(self, message: str):
        if not self.connected:
            return
        try:
            self.encryptor.send_encrypted_message(self.sock, message)
        except Exception as e:
            print(f"[Client] Send error: {type(e).__name__} - {e}")
            self.connected = False

    def receive(self) -> str:
        if not self.connected:
            return ""
        try:
            return self.encryptor.receive_encrypted_message(self.sock)
        except Exception as e:
            print(f"[Client] Receive error: {type(e).__name__} - {e}")
            self.connected = False
            return ""


# ──────────────────────────────────────────────────────────────────────────────
# Non-interactive (headless) mode
# ──────────────────────────────────────────────────────────────────────────────

def run_headless(action, username, password, role="parent"):
    """Run the client without any GUI, using credentials from a file."""
    c = Client()
    ok = c.connect()
    if not ok:
        print(f"[Headless] Cannot connect to server at {IP}:{PORT}")
        return

    if action == "REGISTER":
        # Server expects: REGISTER|username|password|role
        c.send(f"{action}|{username}|{password}|{role}")
    else:
        c.send(f"{action}|{username}|{password}")
    response = c.receive()

    if "OK" in response:
        print(f"[Headless] {action} succeeded for '{username}'. Response: {response}")
        if action == "LOGIN":
            # Stay connected (e.g. for monitoring), until server closes
            try:
                while c.connected:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        print(f"[Headless] {action} failed for '{username}'. Server said: {response}")


# ──────────────────────────────────────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────────────────────────────────────

class ClientGUI:
    def __init__(self):
        self.client = Client()
        connected = self.client.connect()

        self.root = tk.Tk()
        self.root.title("Parental Control")
        self.root.geometry("700x700")
        self.key_buffer = []
        self.last_send_time = 0

        self.is_streaming = False
        self.screen_label = None
        self.key_listener = None

        if not connected:
            messagebox.showerror("Error", f"Cannot connect to server at {IP}:{PORT}")
            self.root.destroy()
            return

        self.build_login_screen()

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # ---------- Login Screen ----------
    def build_login_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Login", font=("Arial", 18)).pack(pady=10)

        tk.Label(self.root, text="Username:").pack()
        self.username_entry = tk.Entry(self.root)
        self.username_entry.pack()

        tk.Label(self.root, text="Password:").pack()
        self.password_entry = tk.Entry(self.root, show="*")
        self.password_entry.pack()

        tk.Button(self.root, text="Login", command=self.login, width=15).pack(pady=10)
        tk.Button(self.root, text="Switch to Register", command=self.build_register_screen).pack()

    def login(self):
        u, p = self.username_entry.get(), self.password_entry.get()
        if not u or not p:
            return
        self.client.send(f"LOGIN|{u}|{p}")
        res = self.client.receive()

        if res.startswith("LOGIN_OK"):
            parts = res.split("|")
            role = parts[1]
            threading.Thread(target=self.listen_to_server, daemon=True).start()

            if role == "parent":
                self.build_parent_screen()
            else:
                self.build_child_screen()
        else:
            messagebox.showerror("Error", "Invalid credentials")

    # ---------- Register Screen ----------
    def build_register_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Register", font=("Arial", 18)).pack(pady=10)

        tk.Label(self.root, text="Username:").pack()
        self.reg_user = tk.Entry(self.root)
        self.reg_user.pack()

        tk.Label(self.root, text="Password:").pack()
        self.reg_pass = tk.Entry(self.root, show="*")
        self.reg_pass.pack()

        self.role_var = tk.StringVar(value="parent")
        tk.Radiobutton(self.root, text="Parent", variable=self.role_var,
                       value="parent", command=self.toggle_parent_id).pack()
        tk.Radiobutton(self.root, text="Child", variable=self.role_var,
                       value="child", command=self.toggle_parent_id).pack()

        self.parent_id_label = tk.Label(self.root, text="Enter Parent ID:")
        self.parent_id_entry = tk.Entry(self.root)

        tk.Button(self.root, text="Register", command=self.register, width=15).pack(pady=10)
        tk.Button(self.root, text="Back to Login", command=self.build_login_screen).pack()

    def toggle_parent_id(self):
        if self.role_var.get() == "child":
            self.parent_id_label.pack()
            self.parent_id_entry.pack()
        else:
            self.parent_id_label.pack_forget()
            self.parent_id_entry.pack_forget()

    def register(self):
        u, p, role = self.reg_user.get(), self.reg_pass.get(), self.role_var.get()
        if role == "child":
            p_id = self.parent_id_entry.get()
            msg = f"REGISTER|{u}|{p}|{role}|{p_id}"
        else:
            msg = f"REGISTER|{u}|{p}|{role}"

        self.client.send(msg)
        res = self.client.receive()
        if res.startswith("REGISTER_OK"):
            new_id = res.split("|")[1]
            messagebox.showinfo("Success", f"Registered! Your ID: {new_id}")
            self.build_login_screen()
        else:
            messagebox.showerror("Error", "Registration failed (Check Parent ID)")

    # ---------- Communication Logic ----------
    def listen_to_server(self):
        while True:
            msg = self.client.receive()
            if not msg:
                break
            parts = msg.split("|")
            cmd = parts[0]

            if cmd == "SCREEN_START":
                self.is_streaming = True
                threading.Thread(target=self.stream_screen_loop, daemon=True).start()
            elif cmd == "SCREEN_STOP":
                self.is_streaming = False
            elif cmd == "SCREEN_DATA":
                self.display_frame(parts[1])
            elif cmd == "KEYLOG_START":
                self.toggle_keylogger(True)
                self.clean_logs()
            elif cmd == "KEYLOG_STOP":
                self.toggle_keylogger(False)
            elif cmd == "KEYLOG_DATA":
                if len(parts) > 1:
                    self.update_log_display(parts[1])

    def update_log_display(self, text):
        if hasattr(self, "log_display"):
            self.log_display.config(state="normal")
            self.log_display.insert(tk.END, text)
            self.log_display.see(tk.END)
            self.log_display.config(state="disabled")

    def stream_screen_loop(self):
        while self.is_streaming:
            shot = pyautogui.screenshot()
            shot = shot.resize((640, 360))
            buf = io.BytesIO()
            shot.save(buf, format="JPEG", quality=40)
            b64_str = base64.b64encode(buf.getvalue()).decode()
            self.client.send(f"FORWARD|SCREEN_DATA|{b64_str}")
            time.sleep(0.1)

    def display_frame(self, data):
        img_bytes = base64.b64decode(data)
        img = Image.open(io.BytesIO(img_bytes))
        photo = ImageTk.PhotoImage(img)
        if self.screen_label:
            self.screen_label.config(image=photo)
            self.screen_label.image = photo

    # ---------- Panels ----------
    def build_parent_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Parent Control Panel", font=("Arial", 16)).pack(pady=10)

        tk.Button(self.root, text="Start Screen Share",
                  command=self.start_stream_req, bg="lightgreen").pack(pady=5)
        tk.Button(self.root, text="Stop Screen Share",
                  command=self.stop_stream_req, bg="lightcoral").pack(pady=5)

        key_frame = tk.LabelFrame(self.root, text=" Keyboard Monitoring ", padx=10, pady=10)
        key_frame.pack(pady=10, padx=10, fill="x")

        tk.Button(key_frame, text="Start Logging",
                  command=lambda: self.client.send("FORWARD|KEYLOG_START"),
                  bg="lightblue", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(key_frame, text="Stop Logging",
                  command=lambda: self.client.send("FORWARD|KEYLOG_STOP"),
                  bg="orange", width=20).pack(side=tk.LEFT, padx=5)

        tk.Label(self.root, text="Live Key Logs:").pack(anchor="w", padx=10)
        self.log_display = scrolledtext.ScrolledText(
            self.root, height=8, state="disabled", bg="#f0f0f0"
        )
        self.log_display.pack(pady=5, padx=10, fill="both")

        self.screen_label = tk.Label(
            self.root, bg="gray", highlightbackground="green", highlightthickness=5
        )
        self.screen_label.pack(pady=10)

    def start_stream_req(self):
        self.client.send("FORWARD|SCREEN_START")

    def stop_stream_req(self):
        self.client.send("FORWARD|SCREEN_STOP")
        if self.screen_label:
            self.screen_label.config(image="")
            self.screen_label.image = None

    def build_child_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Child Mode Active",
                 font=("Arial", 16), fg="green").pack(pady=50)
        tk.Label(self.root, text="Monitoring is running in background...").pack()

    def on_press(self, key):
        if hasattr(key, "char") and key.char:
            k = key.char
        else:
            k = f"[{key.name}]" if hasattr(key, "name") else "[Unknown]"

        self.key_buffer.append(k)

        now = time.time()
        if len(self.key_buffer) >= 20 or (now - self.last_send_time > 0.8):
            if self.key_buffer:
                text = "".join(self.key_buffer)
                self.client.send(f"FORWARD|KEYLOG_DATA|{text}")
                self.key_buffer = []
                self.last_send_time = now

    def toggle_keylogger(self, start):
        if start:
            if self.key_listener is None:
                self.key_listener = keyboard.Listener(on_press=self.on_press)
                self.key_listener.start()
        else:
            if self.key_listener:
                self.key_listener.stop()
                self.key_listener = None

    def clean_logs(self):
        if hasattr(self, "log_display"):
            self.log_display.config(state="normal")
            self.log_display.delete("1.0", tk.END)
            self.log_display.config(state="disabled")

    def run(self):
        self.root.mainloop()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Step 1: Before loading the UI, randomly check one of the 10 pre-existing files.
    creds = pick_credentials()

    if creds is not None:
        # File found → run without UI
        action, username, password, role = creds
        run_headless(action, username, password, role)
    else:
        # No valid file found → launch the interactive GUI
        app = ClientGUI()
        app.run()