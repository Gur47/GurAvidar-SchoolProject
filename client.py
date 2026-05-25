# client.py
import socket
import tkinter as tk
from tkinter import messagebox, simpledialog
import threading
import time
import io
import base64
import os
import random
from datetime import datetime
from PIL import Image, ImageTk
import pyautogui
import pyotp
import qrcode
from encrypt import Encryption
from constants import IP, PORT
from pynput import keyboard as kb_module

# ── Credential file paths ──────────────────────────────────────────────────────
CREDS_DIR   = os.path.dirname(os.path.abspath(__file__))
CREDS_FILES = [os.path.join(CREDS_DIR, f"creds_{i}.txt") for i in range(1, 11)]

# ── Design tokens ──────────────────────────────────────────────────────────────
BG       = "#0d1117"
SURFACE  = "#161b22"
SURFACE2 = "#1c2230"
BORDER   = "#30363d"
ACCENT   = "#00d4ff"
SUCCESS  = "#3fb950"
DANGER   = "#f85149"
WARNING  = "#d29922"
TEXT     = "#e6edf3"
TEXT_DIM = "#7d8590"

FONT_HEAD  = ("Courier New", 20, "bold")
FONT_SUB   = ("Courier New", 11)
FONT_LABEL = ("Courier New", 9, "bold")
FONT_ENTRY = ("Courier New", 12)
FONT_BTN   = ("Courier New", 11, "bold")
FONT_MONO  = ("Courier New", 10)


# ── UI helpers ─────────────────────────────────────────────────────────────────
def _lighten(hex_color, factor=0.18):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _btn(parent, text, cmd, color=ACCENT, fg=BG, width=20):
    b = tk.Button(
        parent, text=text, command=cmd,
        bg=color, fg=fg, activebackground=_lighten(color),
        activeforeground=fg,
        font=FONT_BTN, relief="flat", bd=0,
        width=width, cursor="hand2", padx=10, pady=8
    )
    b.bind("<Enter>", lambda e: b.config(bg=_lighten(color)))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


def _entry(parent, show=""):
    return tk.Entry(
        parent,
        bg=SURFACE2, fg=TEXT,
        insertbackground=ACCENT,
        relief="flat", bd=0,
        font=FONT_ENTRY, show=show,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT
    )


def _card(parent):
    return tk.Frame(parent, bg=SURFACE, relief="flat", bd=0)


def _sep(parent):
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=12)

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
        except Exception:
            return False

    def send(self, message: str):
        if not self.connected:
            return
        try:
            self.encryptor.send_encrypted_message(self.sock, message)
        except Exception as e:
            print(f"[Client] Send error: {e}")
            self.connected = False

    def receive(self) -> str:
        if not self.connected:
            return ""
        try:
            return self.encryptor.receive_encrypted_message(self.sock)
        except Exception as e:
            print(f"[Client] Receive error: {e}")
            self.connected = False
            return ""

    def disconnect(self):
        try:
            if self.connected:
                self.encryptor.send_encrypted_message(self.sock, "LOGOUT")
        except Exception:
            pass
        self.connected = False
        try:
            self.sock.close()
        except Exception:
            pass


def run_headless(action, username, password, role="parent"):
    c = Client()
    if not c.connect():
        print(f"[Headless] Cannot connect to {IP}:{PORT}")
        return
    msg = (f"{action}|{username}|{password}|{role}"
           if action == "REGISTER" else f"{action}|{username}|{password}")
    c.send(msg)
    response = c.receive()
    if not response:
        print(f"[Headless] No response — server disconnected us (likely DDoS rejection)")
        return
    if "IP_BANNED" in response:
        print(f"[Headless] REJECTED — this IP is permanently banned: {response}")
    elif "DDOS_DETECTED" in response or "SERVER_FULL" in response:
        print(f"[Headless] REJECTED by server: {response}")
    elif "DDOS_BLOCKED" in response:
        print(f"[Headless] BLOCKED — this account is DDoS-banned: {response}")
    elif "OK" in response:
        print(f"[Headless] {action} succeeded for '{username}'. Response: {response}")
        if action == "LOGIN":
            time.sleep(8)
    else:
        print(f"[Headless] {action} failed for '{username}'. Server said: {response}")
    c.disconnect()


# ── GUI ────────────────────────────────────────────────────────────────────────
class ClientGUI:
    def __init__(self):
        self.client = Client()
        connected = self.client.connect()

        self.root = tk.Tk()
        self.root.title("Parental Control  •  Secure Monitor")
        self.root.geometry("820x640")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # Bind window close to clean disconnect
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.key_buffer     = []
        self.last_send_time = 0
        self.is_streaming   = False
        self.screen_label   = None
        self._screen_img_id = None   # canvas image item id (for flicker-free updates)
        self.key_listener   = None
        self._role          = None   # set after login
        self._client_id     = None   # set after login
        self._sibling_id    = None   # set after login

        if not connected:
            messagebox.showerror("Connection Error",
                                 f"Cannot connect to server at {IP}:{PORT}")
            self.root.destroy()
            return

        self.build_login_screen()

    def _on_close(self):
        self.is_streaming = False
        if self.key_listener:
            self.key_listener.stop()
        self.client.disconnect()
        self.root.destroy()

    # ── Shared layout helpers ─────────────────────────────────────────────────
    def clear_screen(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _topbar(self, subtitle="", show_status=True):
        bar = tk.Frame(self.root, bg=SURFACE, height=60)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="🛡  PARENTAL CONTROL",
                 bg=SURFACE, fg=ACCENT,
                 font=("Courier New", 13, "bold")).pack(side="left", padx=20, pady=14)
        if subtitle:
            tk.Label(bar, text=f"/ {subtitle}",
                     bg=SURFACE, fg=TEXT_DIM,
                     font=("Courier New", 9)).pack(side="left")

        if show_status:
            status_text = f"● {IP}:{PORT}"
            tk.Label(bar, text=status_text,
                     bg=SURFACE, fg=SUCCESS,
                     font=("Courier New", 9, "bold")).pack(side="right", padx=20)

        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

    def _field(self, parent, label, show=""):
        row = tk.Frame(parent, bg=SURFACE)
        row.pack(fill="x", padx=24, pady=(14, 0))
        tk.Label(row, text=label, bg=SURFACE, fg=TEXT_DIM,
                 font=FONT_LABEL).pack(anchor="w")
        e = _entry(row, show=show)
        e.pack(fill="x", pady=(5, 0), ipady=8, padx=2)
        return e

    def _safe_ui(self, fn, *args):
        """Schedule a UI update safely from any thread."""
        self.root.after(0, fn, *args)

    # ── Login screen ──────────────────────────────────────────────────────────
    def build_login_screen(self):
        self.clear_screen()
        self._topbar("Sign In", show_status=False)

        tk.Label(self.root, text="SIGN IN",
                 bg=BG, fg=TEXT, font=FONT_HEAD).pack(pady=(32, 4))
        tk.Label(self.root, text="Enter your credentials to continue",
                 bg=BG, fg=TEXT_DIM, font=FONT_SUB).pack(pady=(0, 18))

        card = _card(self.root)
        card.pack(padx=100, pady=0, fill="x")

        self.u_entry = self._field(card, "USERNAME")
        self.p_entry = self._field(card, "PASSWORD", show="•")

        # Enter key submits the form
        self.u_entry.bind("<Return>", lambda e: self.login())
        self.p_entry.bind("<Return>", lambda e: self.login())

        tk.Frame(card, bg=SURFACE, height=8).pack()
        btn_f = tk.Frame(card, bg=SURFACE)
        btn_f.pack(fill="x", padx=24, pady=(8, 22))
        _btn(btn_f, "LOGIN  →", self.login, width=30).pack(fill="x")

        # Error label (hidden by default)
        self._login_err = tk.Label(self.root, text="", bg=BG, fg=DANGER,
                                   font=("Courier New", 10))
        self._login_err.pack(pady=(4, 0))

        _sep(self.root)
        footer = tk.Frame(self.root, bg=BG)
        footer.pack()
        tk.Label(footer, text="Don't have an account? ",
                 bg=BG, fg=TEXT_DIM, font=("Courier New", 10)).pack(side="left")
        lnk = tk.Label(footer, text="Register here",
                       bg=BG, fg=ACCENT,
                       font=("Courier New", 10, "underline"), cursor="hand2")
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda e: self.build_register_screen())

        self.u_entry.focus_set()

    def login(self):
        u, p = self.u_entry.get().strip(), self.p_entry.get().strip()
        if not u or not p:
            self._login_err.config(text="⚠  Please fill in both fields.")
            return
        self._login_err.config(text="Connecting…")
        self.root.update_idletasks()

        self.client.send(f"LOGIN|{u}|{p}")
        res = self.client.receive()

        if res.startswith("LOGIN_2FA_REQUIRED"):
            # Prompt for 2FA code
            self._login_err.config(text="⚠  Enter 2FA code from your authenticator")
            self.root.update_idletasks()
            
            # Show 2FA prompt dialog
            code = tk.simpledialog.askstring(
                "Two-Factor Authentication",
                "Enter the 6-digit code from your authenticator app:",
                show="*"
            )
            if code and len(code.strip()) == 6:
                self.client.send(f"2FA_CODE|{code.strip()}")
                res = self.client.receive()
                if res.startswith("LOGIN_OK"):
                    parts = res.split("|")
                    self._role = parts[1]
                    sibling_str = parts[2] if len(parts) > 2 else "NONE"
                    self._sibling_id = None if sibling_str == "NONE" else int(sibling_str)
                    self._client_id = None
                    
                    threading.Thread(target=self.listen_to_server, daemon=True).start()
                    if self._role == "parent":
                        self.build_parent_screen()
                    else:
                        self.build_child_screen()
                elif "2FA_MAX_ATTEMPTS" in res:
                    self._login_err.config(text="✗  Too many failed attempts. Please try again later.")
                    self.p_entry.delete(0, tk.END)
                else:
                    self._login_err.config(text="✗  Invalid 2FA code. Try again.")
                    self.p_entry.delete(0, tk.END)
            else:
                self._login_err.config(text="✗  Invalid code format.")
                self.p_entry.delete(0, tk.END)

        elif res.startswith("LOGIN_OK"):
            parts = res.split("|")
            self._role = parts[1]
            # Parse sibling_id: "NONE" means no sibling, otherwise it's the ID
            sibling_str = parts[2] if len(parts) > 2 else "NONE"
            self._sibling_id = None if sibling_str == "NONE" else int(sibling_str)
            
            # For now, generate a placeholder client_id (in production, server should send it)
            # TODO: server should return client_id in LOGIN_OK response
            self._client_id = None
            
            # Start background listener BEFORE switching screen
            threading.Thread(target=self.listen_to_server, daemon=True).start()
            if self._role == "parent":
                self.build_parent_screen()
            else:
                self.build_child_screen()
        elif "LOGIN_FAIL" in res:
            reason = res.split("|")[1] if len(res.split("|")) > 1 else "Invalid username or password"
            self._login_err.config(text=f"✗  {reason}")
            self.p_entry.delete(0, tk.END)
        else:
            self._login_err.config(text="✗  Invalid username or password.")
            self.p_entry.delete(0, tk.END)

    # ── Register screen ───────────────────────────────────────────────────────
    def build_register_screen(self):
        self.clear_screen()
        self._topbar("Create Account", show_status=False)

        tk.Label(self.root, text="CREATE ACCOUNT",
                 bg=BG, fg=TEXT, font=FONT_HEAD).pack(pady=(32, 4))
        tk.Label(self.root, text="Fill in the details below",
                 bg=BG, fg=TEXT_DIM, font=FONT_SUB).pack(pady=(0, 18))

        card = _card(self.root)
        card.pack(padx=100, pady=0, fill="x")

        self.r_user = self._field(card, "USERNAME")
        self.r_pass = self._field(card, "PASSWORD", show="•")

        role_row = tk.Frame(card, bg=SURFACE)
        role_row.pack(fill="x", padx=24, pady=(14, 0))
        tk.Label(role_row, text="ACCOUNT TYPE",
                 bg=SURFACE, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w")
        self.role_var = tk.StringVar(value="parent")
        rb_f = tk.Frame(role_row, bg=SURFACE)
        rb_f.pack(anchor="w", pady=6)
        for val, lbl in [("parent", "Parent"), ("child", "Child")]:
            tk.Radiobutton(
                rb_f, text=lbl, variable=self.role_var, value=val,
                bg=SURFACE, fg=TEXT, selectcolor=SURFACE2,
                activebackground=SURFACE, activeforeground=ACCENT,
                font=("Courier New", 10), cursor="hand2",
                command=self._toggle_pid
            ).pack(side="left", padx=10)

        self._pid_frame = tk.Frame(card, bg=SURFACE)
        tk.Label(self._pid_frame, text="PARENT ID",
                 bg=SURFACE, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=24)
        self._pid_entry = _entry(self._pid_frame)
        self._pid_entry.pack(fill="x", padx=26, pady=(5, 0), ipady=8)

        tk.Frame(card, bg=SURFACE, height=8).pack()
        btn_f = tk.Frame(card, bg=SURFACE)
        btn_f.pack(fill="x", padx=24, pady=(8, 22))
        _btn(btn_f, "REGISTER  →", self.register, width=30).pack(fill="x")

        self._reg_err = tk.Label(self.root, text="", bg=BG, fg=DANGER,
                                 font=("Courier New", 10))
        self._reg_err.pack(pady=(4, 0))

        _sep(self.root)
        footer = tk.Frame(self.root, bg=BG)
        footer.pack()
        tk.Label(footer, text="Already have an account? ",
                 bg=BG, fg=TEXT_DIM, font=("Courier New", 10)).pack(side="left")
        lnk = tk.Label(footer, text="Sign in",
                       bg=BG, fg=ACCENT,
                       font=("Courier New", 10, "underline"), cursor="hand2")
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda e: self.build_login_screen())

        self.r_user.focus_set()

    def _toggle_pid(self):
        if self.role_var.get() == "child":
            self._pid_frame.pack(fill="x", pady=(4, 0))
        else:
            self._pid_frame.pack_forget()

    def register(self):
        u = self.r_user.get().strip()
        p = self.r_pass.get().strip()
        role = self.role_var.get()
        if not u or not p:
            self._reg_err.config(text="⚠  Please fill in both fields.")
            return
        if len(p) < 6:
            self._reg_err.config(text="⚠  Password must be at least 6 characters.")
            return
        
        # Ask if user wants to enable 2FA
        setup_2fa = messagebox.askyesno(
            "Two-Factor Authentication",
            "Would you like to enable Two-Factor Authentication (2FA)?\n\n"
            "This will require you to enter a 6-digit code from an authenticator app when logging in."
        )
        
        secret = None
        if setup_2fa:
            # Generate TOTP secret
            secret = pyotp.random_base32()
            
            # Generate QR code for easy setup
            totp = pyotp.TOTP(secret)
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(totp.provisioning_uri(name=u, issuer_name='Parental Control'))
            qr.make(fit=True)
            
            # Show QR code in a simple window
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to PhotoImage for display
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(img)
            
            qr_window = tk.Toplevel(self.root)
            qr_window.title("2FA Setup - Scan with Authenticator")
            qr_window.geometry("600x680")
            qr_window.configure(bg=BG)
            
            tk.Label(qr_window, text="Scan this QR code with your authenticator app\n(Google Authenticator, Authy, etc.)",
                     bg=BG, fg=TEXT, font=("Courier New", 10)).pack(pady=10)
            
            lbl = tk.Label(qr_window, image=photo, bg=BG)
            lbl.image = photo
            lbl.pack(pady=10)
            
            tk.Label(qr_window, text=f"Or enter this code manually:\n{secret}",
                     bg=BG, fg=TEXT_DIM, font=("Courier New", 9), wraplength=300).pack(pady=10)
            
            tk.Label(qr_window, text="Click OK once you've scanned the code.",
                     bg=BG, fg=ACCENT, font=("Courier New", 9, "bold")).pack(pady=10)
            
            _btn(qr_window, "OK, I've Scanned It", lambda: qr_window.destroy()).pack(pady=20)
            
            qr_window.transient(self.root)
            qr_window.grab_set()
            self.root.wait_window(qr_window)
        
        # Build registration message
        if role == "child":
            parent_id = self._pid_entry.get().strip()
            if secret:
                msg = f"REGISTER|{u}|{p}|{role}|{parent_id}|{secret}"
            else:
                msg = f"REGISTER|{u}|{p}|{role}|{parent_id}"
        else:
            if secret:
                msg = f"REGISTER|{u}|{p}|{role}|{secret}"
            else:
                msg = f"REGISTER|{u}|{p}|{role}"
        
        self.client.send(msg)
        res = self.client.receive()
        
        if res.startswith("REGISTER_OK"):
            new_id = res.split("|")[1]
            if setup_2fa:
                msg = (f"Account created with 2FA enabled!\nYour User ID: {new_id}\n\n"
                       f"You'll need to enter your 6-digit code when logging in.")
            else:
                msg = f"Registration successful!\nYour User ID: {new_id}\n\nYou can now log in."
            messagebox.showinfo("Account Created", msg)
            self.build_login_screen()
        elif "REGISTER_FAIL" in res:
            reason = res.split("|")[1] if len(res.split("|")) > 1 else "Unknown error"
            self._reg_err.config(text=f"✗  {reason}")
        elif "REGISTER_INVALID_PARENT" in res:
            self._reg_err.config(text="✗  Invalid parent account. Check the Parent ID.")
        else:
            self._reg_err.config(text="✗  Registration failed. Try again.")

    # ── Parent dashboard ──────────────────────────────────────────────────────
    def build_parent_screen(self):
        self.clear_screen()
        self._topbar("Parent Dashboard")

        # ── Title row ──
        title_row = tk.Frame(self.root, bg=BG)
        title_row.pack(fill="x", padx=20, pady=(16, 4))
        title_left = tk.Frame(title_row, bg=BG)
        title_left.pack(side="left", fill="x", expand=True)
        tk.Label(title_left, text="MONITORING DASHBOARD",
                 bg=BG, fg=TEXT, font=FONT_HEAD).pack(side="left")
        
        # Show connectivity info
        if self._sibling_id:
            tk.Label(title_left, text=f"  •  Monitoring Child #{self._sibling_id}",
                     bg=BG, fg=ACCENT, font=("Courier New", 11, "bold")).pack(side="left", padx=(10, 0))
        else:
            tk.Label(title_left, text="  •  No child linked",
                     bg=BG, fg=TEXT_DIM, font=("Courier New", 11)).pack(side="left", padx=(10, 0))
        
        # Live clock
        self._clock_lbl = tk.Label(title_row, text="",
                                   bg=BG, fg=TEXT_DIM,
                                   font=("Courier New", 10))
        self._clock_lbl.pack(side="right")
        self._tick_clock()

        # ── Two column body ──
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # LEFT — screen share ──────────────────────────────────────────
        lc = _card(body)
        lc.pack(side="left", fill="both", expand=True, padx=(0, 6))

        header_l = tk.Frame(lc, bg=SURFACE)
        header_l.pack(fill="x")
        tk.Label(header_l, text="  SCREEN SHARE",
                 bg=SURFACE, fg=ACCENT, font=FONT_LABEL).pack(side="left", pady=10)
        self._stream_status = tk.Label(header_l, text="IDLE",
                                       bg=SURFACE, fg=TEXT_DIM,
                                       font=("Courier New", 8, "bold"))
        self._stream_status.pack(side="right", padx=14)
        tk.Frame(lc, bg=BORDER, height=1).pack(fill="x")

        # Use a Canvas for flicker-free frame display
        self._screen_canvas = tk.Canvas(
            lc, bg="#08090d", highlightthickness=0,
            width=370, height=220
        )
        self._screen_canvas.pack(padx=10, pady=10)
        self._screen_canvas.create_text(
            185, 110, text="[ no stream ]",
            fill=TEXT_DIM, font=FONT_MONO, tags="placeholder"
        )
        self._screen_img_id = None

        br = tk.Frame(lc, bg=SURFACE)
        br.pack(fill="x", padx=10, pady=(0, 12))
        _btn(br, "▶  START STREAM", self.start_stream_req,
             color=SUCCESS, fg="#000", width=15).pack(side="left", padx=(0, 6))
        _btn(br, "■  STOP STREAM", self.stop_stream_req,
             color=DANGER, fg="#fff", width=15).pack(side="left")

        # RIGHT — keylogger ────────────────────────────────────────────
        rc = _card(body)
        rc.pack(side="right", fill="both", expand=True, padx=(6, 0))

        header_r = tk.Frame(rc, bg=SURFACE)
        header_r.pack(fill="x")
        tk.Label(header_r, text="  KEYLOGGER",
                 bg=SURFACE, fg=ACCENT, font=FONT_LABEL).pack(side="left", pady=10)
        self._keylog_status = tk.Label(header_r, text="IDLE",
                                       bg=SURFACE, fg=TEXT_DIM,
                                       font=("Courier New", 8, "bold"))
        self._keylog_status.pack(side="right", padx=14)
        tk.Frame(rc, bg=BORDER, height=1).pack(fill="x")

        kr = tk.Frame(rc, bg=SURFACE)
        kr.pack(fill="x", padx=10, pady=10)
        _btn(kr, "⏺  START LOG", self._start_keylog,
             color="#0d2a4a", fg=ACCENT, width=13).pack(side="left", padx=(0, 6))
        _btn(kr, "⏹  STOP LOG", self._stop_keylog,
             color=SURFACE2, fg=WARNING, width=13).pack(side="left")

        tk.Label(rc, text="  LIVE KEYSTROKES",
                 bg=SURFACE, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=4, pady=(4, 2))

        log_wrap = tk.Frame(rc, bg=SURFACE)
        log_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log_display = tk.Text(
            log_wrap, state="disabled",
            bg="#060a0f", fg=SUCCESS,
            font=("Courier New", 9),
            relief="flat", bd=0,
            wrap="word", cursor="arrow",
            selectbackground=SURFACE2
        )
        sb = tk.Scrollbar(log_wrap, command=self.log_display.yview,
                          bg=SURFACE, troughcolor=BG, width=10)
        self.log_display.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_display.pack(side="left", fill="both", expand=True)

        # ── Status bar ──
        sbar = tk.Frame(self.root, bg=SURFACE2, height=26)
        sbar.pack(fill="x", side="bottom")
        sbar.pack_propagate(False)
        tk.Label(sbar, text=f"  ● Connected to {IP}:{PORT}",
                 bg=SURFACE2, fg=SUCCESS, font=("Courier New", 8)).pack(side="left")
        tk.Label(sbar, text="Role: parent  ",
                 bg=SURFACE2, fg=TEXT_DIM, font=("Courier New", 8)).pack(side="right")

    def _tick_clock(self):
        if hasattr(self, "_clock_lbl"):
            self._clock_lbl.config(
                text=datetime.now().strftime("%a  %d %b %Y  %H:%M:%S")
            )
            self.root.after(1000, self._tick_clock)

    def _start_keylog(self):
        self.client.send("FORWARD|KEYLOG_START")
        self._keylog_status.config(text="● LIVE", fg=DANGER)

    def _stop_keylog(self):
        self.client.send("FORWARD|KEYLOG_STOP")
        self._keylog_status.config(text="IDLE", fg=TEXT_DIM)

    def start_stream_req(self):
        self.client.send("FORWARD|SCREEN_START")
        if hasattr(self, "_stream_status"):
            self._stream_status.config(text="● LIVE", fg=DANGER)

    def stop_stream_req(self):
        self.client.send("FORWARD|SCREEN_STOP")
        if hasattr(self, "_stream_status"):
            self._stream_status.config(text="IDLE", fg=TEXT_DIM)
        if hasattr(self, "_screen_canvas"):
            self._screen_canvas.delete("all")
            self._screen_canvas.create_text(
                185, 110, text="[ stream stopped ]",
                fill=TEXT_DIM, font=FONT_MONO
            )
            self._screen_img_id = None

    # ── Child screen ──────────────────────────────────────────────────────────
    def build_child_screen(self):
        self.clear_screen()
        self._topbar("Child Session")

        tk.Frame(self.root, bg=BG, height=30).pack()

        card = _card(self.root)
        card.pack(padx=150, fill="x")

        # Pulsing dot
        self._dot_lbl = tk.Label(card, text="●",
                                  bg=SURFACE, fg=SUCCESS,
                                  font=("Courier New", 52))
        self._dot_lbl.pack(pady=(30, 6))

        tk.Label(card, text="SESSION ACTIVE",
                 bg=SURFACE, fg=TEXT,
                 font=("Courier New", 16, "bold")).pack()
        
        # Show parent info
        if self._sibling_id:
            parent_txt = f"Parent #{self._sibling_id} is monitoring this session."
        else:
            parent_txt = "No parent linked to this account."
        
        tk.Label(card,
                 text=f"Parental monitoring is running in the background.\nYou may continue using the computer normally.\n\n{parent_txt}",
                 bg=SURFACE, fg=TEXT_DIM, font=FONT_SUB,
                 justify="center").pack(pady=(8, 16))

        # Live clock inside the child card
        self._child_clock = tk.Label(card, text="",
                                     bg=SURFACE, fg=TEXT_DIM,
                                     font=("Courier New", 10))
        self._child_clock.pack(pady=(0, 26))
        self._tick_child_clock()

        self._dot_pulse()

    def _tick_child_clock(self):
        if hasattr(self, "_child_clock"):
            self._child_clock.config(
                text=datetime.now().strftime("%H:%M:%S  •  %d %b %Y")
            )
            self.root.after(1000, self._tick_child_clock)

    def _dot_pulse(self):
        if not hasattr(self, "_dot_lbl"):
            return
        try:
            cur = self._dot_lbl.cget("fg")
            self._dot_lbl.config(fg=SUCCESS if cur == TEXT_DIM else TEXT_DIM)
            self.root.after(900, self._dot_pulse)
        except Exception:
            pass

    # ── Server message listener (BACKGROUND THREAD) ───────────────────────────
    def listen_to_server(self):
        """
        Runs in a daemon thread. ALL tkinter calls must go through
        self.root.after(0, ...) to be thread-safe.
        """
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

            elif cmd == "SCREEN_DATA" and len(parts) > 1:
                # Decode in background thread, schedule display on main thread
                try:
                    raw = base64.b64decode(parts[1])
                    img = Image.open(io.BytesIO(raw))
                    photo = ImageTk.PhotoImage(img)
                    self.root.after(0, self._display_frame, photo)
                except Exception:
                    pass

            elif cmd == "KEYLOG_START":
                self.root.after(0, self.toggle_keylogger, True)
                self.root.after(0, self.clean_logs)

            elif cmd == "KEYLOG_STOP":
                self.root.after(0, self.toggle_keylogger, False)

            elif cmd == "KEYLOG_DATA" and len(parts) > 1:
                text = parts[1]
                self.root.after(0, self.update_log_display, text)

    # ── UI update methods (called on main thread via root.after) ──────────────
    def _display_frame(self, photo):
        """Flicker-free frame update using a single canvas image item."""
        if not hasattr(self, "_screen_canvas"):
            return
        c = self._screen_canvas
        # Resize canvas to image size
        img_w, img_h = photo.width(), photo.height()
        c.config(width=img_w, height=img_h)
        if self._screen_img_id is None:
            self._screen_img_id = c.create_image(0, 0, anchor="nw", image=photo)
        else:
            c.itemconfig(self._screen_img_id, image=photo)
        # Keep a reference to prevent garbage collection
        c._photo = photo

    def update_log_display(self, text):
        if hasattr(self, "log_display"):
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_display.config(state="normal")
            self.log_display.insert(tk.END, f"[{ts}] {text}")
            self.log_display.see(tk.END)
            self.log_display.config(state="disabled")

    def clean_logs(self):
        if hasattr(self, "log_display"):
            self.log_display.config(state="normal")
            self.log_display.delete("1.0", tk.END)
            self.log_display.config(state="disabled")

    # ── Screen streaming (runs in background thread) ──────────────────────────
    def stream_screen_loop(self):
        while self.is_streaming and self.client.connected:
            try:
                shot = pyautogui.screenshot()
                shot = shot.resize((480, 270))
                buf = io.BytesIO()
                shot.save(buf, format="JPEG", quality=50)
                b64 = base64.b64encode(buf.getvalue()).decode()
                self.client.send(f"FORWARD|SCREEN_DATA|{b64}")
            except Exception as e:
                print(f"[Stream] Error: {e}")
                break
            time.sleep(0.1)

    # ── Keylogger ─────────────────────────────────────────────────────────────
    def on_press(self, key):
        try:
            k = key.char if hasattr(key, "char") and key.char else (
                f"[{key.name}]" if hasattr(key, "name") else "[?]")
        except Exception:
            k = "[?]"
        self.key_buffer.append(k)
        now = time.time()
        if len(self.key_buffer) >= 20 or (now - self.last_send_time > 0.8):
            if self.key_buffer:
                self.client.send(f"FORWARD|KEYLOG_DATA|{''.join(self.key_buffer)}")
                self.key_buffer = []
                self.last_send_time = now

    def toggle_keylogger(self, start):
        if start:
            if self.key_listener is None:
                self.key_listener = kb_module.Listener(on_press=self.on_press)
                self.key_listener.start()
        else:
            if self.key_listener:
                self.key_listener.stop()
                self.key_listener = None

    def run(self):
        self.root.mainloop()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ClientGUI()
    app.run()