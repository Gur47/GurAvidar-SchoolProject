# server.py
import socket
import threading
import tools_no_encryption
import os
import datetime
import pyotp
import tkinter as tk
from tkinter import scrolledtext, font as tkfont
from db_manager import DatabaseManager
from create_tables import create_all_tables
from constants import SERVER_BIND_IP, SERVER_IP, PORT, MAX_TOTAL_CONNECTIONS, MAX_CONNECTIONS_PER_IP, DB_NAME
from encrypt import Encryption

# ── Keylog files go into the keylogs/ subfolder ──────────────────────────────
_HERE       = os.path.dirname(os.path.abspath(__file__))
KEYLOGS_DIR = os.path.join(_HERE, "keylogs")

# ── Design tokens (matching client dark theme) ────────────────────────────────
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


# ══════════════════════════════════════════════════════════════════════════════
# Server logic (no UI dependencies)
# ══════════════════════════════════════════════════════════════════════════════
class Server:
    def __init__(self, ui_callback=None):
        """
        ui_callback: optional function(event_type, message) called from
        any thread to push events to the UI.
        event_type: "connect" | "disconnect" | "ddos" | "login" |
                    "register" | "keylog" | "info" | "error"
        """
        self.ui_callback = ui_callback or (lambda t, m: None)

        self.db = DatabaseManager(
            "localhost", "root", "2wsx3edc4rfv", DB_NAME
        )
        self.encryptor = Encryption()
        self.clients      = {}   # client_id -> socket
        self.lock         = threading.Lock()
        self.clients_logs = {}   # child_id  -> list[str]
        self.waiting_2fa  = {}   # client_id -> {secret, attempts}

        # DDoS tracking
        self.ip_connections   = {}   # ip -> [client_ids]
        self.active_sockets   = {}
        self.total_connections = 0

        os.makedirs(KEYLOGS_DIR, exist_ok=True)

        try:
            tables = self.db.show_tables()
            if "clients" not in tables:
                create_all_tables(self.db)
            else:
                # הוסף את העמודה client_ip_banned אם לא קיימת (migration)
                self._ensure_ip_banned_column()
        except Exception:
            create_all_tables(self.db)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _ensure_ip_banned_column(self):
        """
        Migration: מוסיף את העמודה client_ip_banned לטבלת clients אם היא לא קיימת.
        נדרש פעם אחת בלבד — כשמעדכנים מגרסה ישנה.
        """
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("SHOW COLUMNS FROM clients LIKE 'client_ip_banned'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE clients ADD COLUMN client_ip_banned BOOLEAN DEFAULT FALSE"
                )
                self.db.conn.commit()
                self._log("info", "Migration: added column client_ip_banned to clients table")
            # Ensure 2FA columns exist
            cursor.execute("SHOW COLUMNS FROM clients LIKE 'client_2fa_enabled'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE clients ADD COLUMN client_2fa_enabled BOOLEAN DEFAULT FALSE"
                )
                self.db.conn.commit()
                self._log("info", "Migration: added column client_2fa_enabled to clients table")

            cursor.execute("SHOW COLUMNS FROM clients LIKE 'client_2fa_secret'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE clients ADD COLUMN client_2fa_secret VARCHAR(255)"
                )
                self.db.conn.commit()
                self._log("info", "Migration: added column client_2fa_secret to clients table")
        except Exception as e:
            self._log("error", f"Migration error: {e}")

    def _validate_username(self, username):
        """Validate username format (alphanumeric, 3-32 chars)."""
        if not username or len(username) < 3 or len(username) > 32:
            return False
        return username.replace("_", "").replace("-", "").isalnum()

    def _validate_password(self, password):
        """Validate password (at least 6 chars)."""
        return password and len(password) >= 6

    def _validate_role(self, role):
        """Validate role is one of allowed values."""
        return role in ("parent", "child")

    def _log(self, event_type, message):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.ui_callback(event_type, f"[{ts}] {message}")

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((SERVER_BIND_IP, PORT))
        srv.listen()
        self._log("info", f"Server listening on {SERVER_BIND_IP}:{PORT} (LAN clients should connect to {SERVER_IP}:{PORT})")
        self._log("info", f"Limits — Max total: {MAX_TOTAL_CONNECTIONS}, Max per IP: {MAX_CONNECTIONS_PER_IP}")

        while True:
            client_socket, addr = srv.accept()
            client_ip = addr[0]
            client_port = addr[1]
            threading.Thread(
                target=self.handle_client,
                args=(client_socket, client_ip, client_port),
                daemon=True
            ).start()

    # ── Connection tracking ───────────────────────────────────────────────────
    def _register_connection(self, client_id, client_ip, client_socket):
        with self.lock:
            self.total_connections += 1
            self.ip_connections.setdefault(client_ip, []).append(client_id)
            self.clients[client_id] = client_socket
        self.ui_callback("connect", {
            "client_id": client_id,
            "ip": client_ip,
            "total": self.total_connections
        })

    def _unregister_connection(self, client_id, client_ip, username=None):
        with self.lock:
            self.clients.pop(client_id, None)
            if client_ip and client_ip in self.ip_connections:
                try:
                    self.ip_connections[client_ip].remove(client_id)
                except ValueError:
                    pass
                if not self.ip_connections[client_ip]:
                    del self.ip_connections[client_ip]
            if self.total_connections > 0:
                self.total_connections -= 1
        self.ui_callback("disconnect", {
            "client_id": client_id,
            "ip": client_ip,
            "username": username or f"id={client_id}",
            "total": self.total_connections
        })

    def _check_global_limit(self):
        with self.lock:
            return self.total_connections >= MAX_TOTAL_CONNECTIONS

    def _check_ip_limit(self, client_ip):
        with self.lock:
            return len(self.ip_connections.get(client_ip, [])) >= MAX_CONNECTIONS_PER_IP
    
    def _would_exceed_global_limit(self):
        """Check if adding one more connection would exceed global limit."""
        with self.lock:
            return self.total_connections >= MAX_TOTAL_CONNECTIONS
    
    def _would_exceed_ip_limit(self, client_ip):
        """Check if adding one more connection from this IP would exceed limit."""
        with self.lock:
            return len(self.ip_connections.get(client_ip, [])) >= MAX_CONNECTIONS_PER_IP

    def _is_ip_banned(self, client_ip):
        """
        בודק אם ה-IP חסום — מחפש בטבלת clients שורה עם IP זה
        שהעמודה client_ip_banned שלה היא TRUE.
        אין טבלת banned_ips. החסימה נשמרת ישירות בעמודת הלקוח.
        """
        try:
            rows = self.db.get_rows_with_value("clients", "client_ip", client_ip)
            for row in rows:
                # client_ip_banned is expected at index 10
                if len(row) > 10 and row[10]:
                    return True
        except Exception:
            pass
        return False

    def _ban_ip(self, client_ip):
        """
        מסמן client_ip_banned=TRUE לכל השורות בטבלת clients עם ה-IP הזה.
        זו החסימה הקבועה — אין דרך לבטל אותה דרך השרת.
        """
        try:
            rows = self.db.get_rows_with_value("clients", "client_ip", client_ip)
            for row in rows:
                self.db.update_row("clients", "client_id", row[0],
                                   ["client_ip_banned", "client_ddos_status"], [True, True])
            self._log("info", f"  Banned IP {client_ip} — {len(rows)} client row(s) flagged in DB")
        except Exception as e:
            self._log("error", f"Failed to ban IP {client_ip}: {e}")

    def _flag_ddos(self, client_ip):
        with self.lock:
            affected = list(self.ip_connections.get(client_ip, []))

        # סמן client_ip_banned=TRUE לכל השורות עם IP זה בטבלת clients
        self._ban_ip(client_ip)

        # סגור את כל הסוקטים מה-IP הזה
        with self.lock:
            sockets_to_close = [self.clients[c] for c in affected if c in self.clients]

        for s in sockets_to_close:
            try:
                s.close()
            except Exception:
                pass

        # נקה את מבני הנתונים
        with self.lock:
            for cid in affected:
                self.clients.pop(cid, None)
            if client_ip in self.ip_connections:
                del self.ip_connections[client_ip]
            self.total_connections = max(0, self.total_connections - len(affected))

        self._log("ddos",
                  f"🛑 DDoS flagged IP {client_ip} — "
                  f"{len(affected)} session(s) killed, IP permanently banned (client_ip_banned=TRUE)")
        self.ui_callback("ddos", {"ip": client_ip, "count": len(affected)})

    def _notify_parent_sibling_online(self, parent_id, child_id):
        """
        Send a notification to the parent that their child has connected.
        Called when a child successfully logs in or registers.
        """
        with self.lock:
            if parent_id in self.clients:
                parent_socket = self.clients[parent_id]
                try:
                    self.encryptor.send_encrypted_message(
                        parent_socket,
                        f"SIBLING_ONLINE|{child_id}"
                    )
                    self._log("info", f"  📢 Notified parent {parent_id} that child {child_id} came online")
                except Exception as e:
                    self._log("error", f"Failed to notify parent {parent_id}: {e}")

    # ── Main client handler ───────────────────────────────────────────────────
    def handle_client(self, client_socket, client_ip, client_port):
        client_id = None
        sibling_id = None
        username = None

        if self._is_ip_banned(client_ip):
            self._log("ddos", f"🔒 Permanently banned IP {client_ip} tried to connect — rejected instantly")
            try:
                self.encryptor.send_encrypted_message(client_socket, "REJECTED|IP_BANNED")
            except Exception:
                pass
            client_socket.close()
            return

        if self._would_exceed_global_limit():
            self._log("error", f"⛔ Global limit ({MAX_TOTAL_CONNECTIONS}) reached — rejected {client_ip}")
            try:
                self.encryptor.send_encrypted_message(client_socket, "REJECTED|SERVER_FULL")
            except Exception:
                pass
            client_socket.close()
            return

        if self._would_exceed_ip_limit(client_ip):
            self._log("ddos",
                      f"🚨 DDoS DETECTED — IP {client_ip} opened >{MAX_CONNECTIONS_PER_IP} connections! "
                      f"Banning all sessions from this address.")
            try:
                self.encryptor.send_encrypted_message(client_socket, "REJECTED|DDOS_DETECTED")
            except Exception:
                pass
            client_socket.close()
            self._flag_ddos(client_ip)
            return

        try:
            while True:
                request = self.encryptor.receive_encrypted_message(client_socket)
                if not request:
                    break

                parts   = request.split("|")
                command = parts[0]

                # ── LOGIN ─────────────────────────────────────────────────────
                if command == "LOGIN":
                    if len(parts) < 3:
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL|Invalid format")
                        continue

                    username, password = parts[1], parts[2]
                    
                    # Validate input
                    if not self._validate_username(username):
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL|Invalid username format")
                        self._log("info", f"  Login FAIL (invalid username format) '{username}' from {client_ip}")
                        continue

                    ph    = tools_no_encryption.get_hash_value(password)
                    users = self.db.get_rows_with_value("clients", "client_username", username)

                    if not users:
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL")
                        self._log("info", f"  Login FAIL (unknown user) '{username}' from {client_ip}")
                        continue

                    user = users[0]
                    if user[4] != ph:
                        self.encryptor.send_encrypted_message(
                            client_socket, "LOGIN_FAIL|Wrong password")
                        self._log("info", f"  Login FAIL (wrong pwd) '{username}' from {client_ip}")
                        continue

                    client_id  = user[0]
                    role       = user[5]
                    sibling_id = user[6]
                    
                    # Check if 2FA is enabled (index 11)
                    has_2fa = False
                    if len(user) > 11 and user[11]:
                        has_2fa = True
                        secret = user[12] if len(user) > 12 else None
                    
                    if has_2fa and secret:
                        # Store session for 2FA verification (max 3 attempts, 5 min timeout)
                        self.waiting_2fa[client_id] = {
                            "socket": client_socket,
                            "username": username,
                            "role": role,
                            "sibling_id": sibling_id,
                            "secret": secret,
                            "attempts": 0,
                            "client_ip": client_ip
                        }
                        self._log("login", f"🔐 Login step 1/2 — '{username}' requires 2FA code")
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_2FA_REQUIRED")
                    else:
                        # No 2FA — proceed directly
                        try:
                            self.db.update_row("clients", "client_id", client_id,
                                               ["client_ip"], [client_ip])
                        except Exception:
                            pass

                        self._register_connection(client_id, client_ip, client_socket)
                        self._log("login", f"✅ Login OK  '{username}'  role={role}  id={client_id}  ip={client_ip}")

                        response = f"LOGIN_OK|{role}|{sibling_id if sibling_id else 'NONE'}|{client_id}"
                        self.encryptor.send_encrypted_message(client_socket, response)
                        
                        # Notify parent if this is a child account
                        if role == "child" and sibling_id:
                            self._notify_parent_sibling_online(sibling_id, client_id)

                # ── REGISTER ──────────────────────────────────────────────────
                elif command == "REGISTER":
                    if len(parts) < 4:
                        self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Invalid format")
                        continue

                    username, password, role = parts[1], parts[2], parts[3].lower()
                    
                    # Validate inputs
                    if not self._validate_username(username):
                        self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Invalid username format")
                        continue
                    
                    if not self._validate_password(password):
                        self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Password must be at least 6 characters")
                        continue
                    
                    if not self._validate_role(role):
                        self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Invalid role")
                        continue

                    # Check if username already exists
                    existing = self.db.get_rows_with_value("clients", "client_username", username)
                    if existing:
                        self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Username already taken")
                        self._log("register", f"  Register FAIL (duplicate username) '{username}' from {client_ip}")
                        continue

                    ph = tools_no_encryption.get_hash_value(password)

                    p_id = None
                    secret_2fa = None
                    
                    if role == "child":
                        if len(parts) < 5:
                            self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Parent ID required for child account")
                            continue
                        try:
                            p_id = int(parts[4])
                        except ValueError:
                            self.encryptor.send_encrypted_message(client_socket, "REGISTER_FAIL|Invalid parent ID")
                            continue
                        
                        parent_rows = self.db.get_rows_with_value(
                            "clients", "client_id", p_id)
                        if (not parent_rows
                                or parent_rows[0][5] != "parent"
                                or parent_rows[0][6] is not None):
                            self.encryptor.send_encrypted_message(
                                client_socket, "REGISTER_INVALID_PARENT")
                            continue
                        
                        # Check for 2FA secret (would be at index 5 for child)
                        if len(parts) > 5:
                            secret_2fa = parts[5]
                    else:
                        # Check for 2FA secret (would be at index 4 for parent)
                        if len(parts) > 4:
                            secret_2fa = parts[4]

                    # Standard registration (no parent approval needed)
                    new_id = self.db.insert_row(
                        "clients",
                        "(client_ip, client_port, client_username, client_password, "
                        "client_role, client_sibling_id, client_ddos_status, "
                        "client_total_audio_logs, client_total_keylogs)",
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (client_ip, client_port, username, ph, role, None, False, 0, 0)
                    )

                    # Enable 2FA if secret was provided
                    if secret_2fa:
                        try:
                            self.db.update_row("clients", "client_id", new_id,
                                               ["client_2fa_enabled", "client_2fa_secret"], 
                                               [True, secret_2fa])
                            self._log("register", f"🔐  2FA enabled for new user '{username}' (id={new_id})")
                        except Exception as e:
                            self._log("error", f"Failed to enable 2FA for {username}: {e}")

                    if role == "child" and p_id:
                        self.db.update_row("clients", "client_id", new_id,
                                           ["client_sibling_id"], [p_id])
                        self.db.update_row("clients", "client_id", p_id,
                                           ["client_sibling_id"], [new_id])

                    self._log("register",
                              f"📝 Register OK  '{username}'  role={role}  new_id={new_id}  ip={client_ip}")
                    self.encryptor.send_encrypted_message(
                        client_socket, f"REGISTER_OK|{new_id}")

                # ── FORWARD ───────────────────────────────────────────────────
                elif command == "FORWARD":
                    payload = request[len("FORWARD|"):]

                    if payload.startswith("KEYLOG_START"):
                        if sibling_id is not None:
                            self.clients_logs[sibling_id] = []

                    elif payload.startswith("KEYLOG_DATA|"):
                        data = payload.split("|", 1)[1] if "|" in payload else ""
                        if client_id in self.clients_logs:
                            self.clients_logs[client_id].append(data)

                    elif payload.startswith("KEYLOG_STOP"):
                        if sibling_id in self.clients_logs and self.clients_logs[sibling_id]:
                            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            fname    = f"log_{sibling_id}_{ts}.txt"
                            fpath    = os.path.join(KEYLOGS_DIR, fname)
                            full_log = "".join(self.clients_logs[sibling_id])

                            with open(fpath, "w", encoding="utf-8", errors="replace") as f:
                                f.write(full_log)

                            self.db.insert_row(
                                "keylogs",
                                "(keylog_parent_id, keylog_child_id, keylog_path_name)",
                                "(%s, %s, %s)",
                                (client_id, sibling_id, fpath)
                            )
                            del self.clients_logs[sibling_id]
                            self._log("keylog",
                                      f"💾 Keylog saved → {fname}  (parent={client_id}, child={sibling_id})")

                    with self.lock:
                        if sibling_id and sibling_id in self.clients:
                            self.encryptor.send_encrypted_message(
                                self.clients[sibling_id], payload)

                elif command == "LOGOUT":
                    break
                # ── 2FA Code verification (TOTP) ───────────────────────────────
                elif command == "2FA_CODE":
                    # Format: 2FA_CODE|<code>
                    if len(parts) < 2:
                        continue
                    
                    code = parts[1].strip()
                    
                    # Find which client is waiting for 2FA
                    for cid, session in list(self.waiting_2fa.items()):
                        if session.get("socket") == client_socket:
                            secret = session.get("secret")
                            session["attempts"] += 1
                            
                            # Validate TOTP code (allow current and previous 30-sec window)
                            try:
                                totp = pyotp.TOTP(secret)
                                # Check current window and 1 window back for tolerance
                                if totp.verify(code, valid_window=1):
                                    # Code is valid!
                                    username = session.get("username")
                                    role = session.get("role")
                                    sibling_id = session.get("sibling_id")
                                    
                                    try:
                                        self.db.update_row("clients", "client_id", cid,
                                                           ["client_ip"], [session.get("client_ip")])
                                    except Exception:
                                        pass
                                    
                                    self._register_connection(cid, session.get("client_ip"), client_socket)
                                    self._log("login", f"✅ Login OK  '{username}'  role={role}  id={cid}  ip={session.get('client_ip')}")
                                    
                                    response = f"LOGIN_OK|{role}|{sibling_id if sibling_id else 'NONE'}|{cid}"
                                    self.encryptor.send_encrypted_message(client_socket, response)
                                    
                                    # Notify parent if this is a child account
                                    if role == "child" and sibling_id:
                                        self._notify_parent_sibling_online(sibling_id, cid)
                                    
                                    # Clean up
                                    del self.waiting_2fa[cid]
                                    break
                                else:
                                    # Invalid code
                                    if session["attempts"] >= 3:
                                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL|2FA_MAX_ATTEMPTS")
                                        self._log("login", f"❌ 2FA failed (max attempts) for '{session.get('username')}'")
                                        del self.waiting_2fa[cid]
                                        break
                                    else:
                                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL|2FA_INVALID_CODE")
                                        break
                            except Exception as e:
                                self._log("error", f"2FA validation error: {e}")
                                self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL|2FA_ERROR")
                                del self.waiting_2fa[cid]
                                break


        except Exception as e:
            self._log("error", f"❌ Error ({client_ip}): {type(e).__name__} — {e}")

        finally:
            self._unregister_connection(client_id, client_ip, username)
            try:
                client_socket.close()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Server UI dashboard
# ══════════════════════════════════════════════════════════════════════════════
class ServerUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Parental Control — Server Dashboard")
        self.root.configure(bg=BG)
        self.root.geometry("960x680")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._active_rows = {}   # client_id -> row frame
        self._ddos_count  = 0

        self._build_ui()
        self._server = None

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ──
        topbar = tk.Frame(self.root, bg=SURFACE, height=60)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="🛡  PARENTAL CONTROL",
                 bg=SURFACE, fg=ACCENT,
                 font=("Courier New", 14, "bold")).pack(side="left", padx=20, pady=14)
        tk.Label(topbar, text="SERVER DASHBOARD",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 10)).pack(side="left")

        self._status_lbl = tk.Label(topbar, text="● STARTING…",
                                     bg=SURFACE, fg=WARNING,
                                     font=("Courier New", 10, "bold"))
        self._status_lbl.pack(side="right", padx=20)

        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

        # ── Stats bar ──
        stats = tk.Frame(self.root, bg=SURFACE2, height=48)
        stats.pack(fill="x")
        stats.pack_propagate(False)
        # Small title for clarity
        tk.Label(stats, text="STATS",
             bg=SURFACE2, fg=TEXT_DIM,
             font=("Courier New", 9, "bold")).pack(side="left", padx=12)

        for label, attr, color in [
            ("ACTIVE CONNECTIONS", "_stat_conn", ACCENT),
            ("MAX ALLOWED",        "_stat_max",  TEXT_DIM),
            ("DDOS EVENTS",        "_stat_ddos", DANGER),
            ("KEYLOGS SAVED",      "_stat_klog", SUCCESS),
        ]:
            cell = tk.Frame(stats, bg=SURFACE2)
            cell.pack(side="left", padx=20, pady=6)
            
            # Label on top, number below
            tk.Label(cell, text=label,
                     bg=SURFACE2, fg=TEXT_DIM,
                     font=("Courier New", 7)).pack()
            lbl = tk.Label(cell, text="0",
                           bg=SURFACE2, fg=color,
                           font=("Courier New", 18, "bold"))
            lbl.pack()
            setattr(self, attr, lbl)

        self._stat_max.config(text=str(MAX_TOTAL_CONNECTIONS))
        self._stat_conn.config(text="0")
        self._stat_ddos.config(text="0")
        self._stat_klog.config(text="0")

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # ── MAIN BODY: Top half (MySQL viewer) + Bottom half (User list + Logs) ──
        main_body = tk.Frame(self.root, bg=BG)
        main_body.pack(fill="both", expand=True, padx=8, pady=8)

        # ═══ TOP HALF: MySQL Interface (Clients Table) ═══
        top_section = tk.Frame(main_body, bg=BG)
        top_section.pack(fill="both", expand=True, pady=(0, 6))

        tk.Label(top_section, text="DATABASE VIEW — Clients Table",
                 bg=BG, fg=ACCENT,
                 font=("Courier New", 10, "bold")).pack(anchor="w", pady=(0, 4))

        db_frame = tk.Frame(top_section, bg=SURFACE, relief="flat")
        db_frame.pack(fill="both", expand=True)

        # Table header
        header = tk.Frame(db_frame, bg="#0a0e14")
        header.pack(fill="x")
        for col, width in [("ID", 50), ("IP", 200), ("PORT", 60), ("USER", 110),
                           ("ROLE", 60), ("SIBLING", 70), ("BANNED", 60)]:
            tk.Label(header, text=col, bg="#0a0e14", fg=TEXT_DIM,
                     font=("Courier New", 9, "bold"),
                     width=width // 8, anchor="w").pack(side="left", padx=4, pady=3)
        tk.Frame(db_frame, bg=BORDER, height=1).pack(fill="x")

        # Scrollable table canvas
        self._db_canvas = tk.Canvas(db_frame, bg=SURFACE, highlightthickness=0,
                                     height=120)
        self._db_scroll = tk.Scrollbar(db_frame, orient="vertical",
                                        command=self._db_canvas.yview, bg=SURFACE)
        self._db_canvas.configure(yscrollcommand=self._db_scroll.set)
        self._db_scroll.pack(side="right", fill="y")
        self._db_canvas.pack(side="left", fill="both", expand=True)

        self._db_inner = tk.Frame(self._db_canvas, bg=SURFACE)
        self._db_canvas.create_window((0, 0), window=self._db_inner, anchor="nw")
        self._db_inner.bind("<Configure>",
            lambda e: self._db_canvas.configure(scrollregion=self._db_canvas.bbox("all")))

        self._db_rows = {}  # client_id -> row frame

        # ═══ BOTTOM HALF: Two columns (Users + Logs) ═══
        bottom_section = tk.Frame(main_body, bg=BG)
        bottom_section.pack(fill="both", expand=True)

        # LEFT: Active connections (quarter)
        left_quarter = tk.Frame(bottom_section, bg=BG)
        left_quarter.pack(side="left", fill="both", expand=True, padx=(0, 4))

        tk.Label(left_quarter, text="CONNECTED USERS",
                 bg=BG, fg=ACCENT,
                 font=("Courier New", 10, "bold")).pack(anchor="w", pady=(0, 4))

        conn_frame = tk.Frame(left_quarter, bg=SURFACE)
        conn_frame.pack(fill="both", expand=True)

        # Scrollable users list
        self._conn_canvas = tk.Canvas(conn_frame, bg=SURFACE, highlightthickness=0)
        self._conn_scroll = tk.Scrollbar(conn_frame, orient="vertical",
                                          command=self._conn_canvas.yview, bg=SURFACE)
        self._conn_canvas.configure(yscrollcommand=self._conn_scroll.set)
        self._conn_scroll.pack(side="right", fill="y")
        self._conn_canvas.pack(side="left", fill="both", expand=True)

        self._conn_inner = tk.Frame(self._conn_canvas, bg=SURFACE)
        self._conn_canvas.create_window((0, 0), window=self._conn_inner, anchor="nw")
        self._conn_inner.bind("<Configure>",
            lambda e: self._conn_canvas.configure(scrollregion=self._conn_canvas.bbox("all")))

        self._active_rows = {}

        # RIGHT: Event log (quarter)
        right_quarter = tk.Frame(bottom_section, bg=BG)
        right_quarter.pack(side="right", fill="both", expand=True, padx=(4, 0))

        tk.Label(right_quarter, text="EVENT LOG",
                 bg=BG, fg=ACCENT,
                 font=("Courier New", 10, "bold")).pack(anchor="w", pady=(0, 4))

        self._log_box = tk.Text(
            right_quarter, state="disabled",
            bg="#060a0f", fg=SUCCESS,
            font=("Courier New", 8),
            relief="flat", bd=0,
            wrap="word", cursor="arrow"
        )
        sb = tk.Scrollbar(right_quarter, command=self._log_box.yview, bg=SURFACE)
        self._log_box.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log_box.pack(side="left", fill="both", expand=True)

        # Colour tags for log
        self._log_box.tag_configure("info",     foreground=TEXT_DIM)
        self._log_box.tag_configure("login",    foreground=SUCCESS)
        self._log_box.tag_configure("register", foreground=ACCENT)
        self._log_box.tag_configure("connect",  foreground=ACCENT)
        self._log_box.tag_configure("disconnect",foreground=TEXT_DIM)
        self._log_box.tag_configure("ddos",     foreground=DANGER)
        self._log_box.tag_configure("error",    foreground=DANGER)
        self._log_box.tag_configure("keylog",   foreground=SUCCESS)

        # ── Status bar ──
        sbar = tk.Frame(self.root, bg=SURFACE2, height=26)
        sbar.pack(fill="x", side="bottom")
        sbar.pack_propagate(False)
        tk.Label(sbar, text=f"  {SERVER_IP}:{PORT}",
                 bg=SURFACE2, fg=TEXT_DIM,
                 font=("Courier New", 8)).pack(side="left")
        self._clock_lbl = tk.Label(sbar, text="",
                                    bg=SURFACE2, fg=TEXT_DIM,
                                    font=("Courier New", 8))
        self._clock_lbl.pack(side="right", padx=8)
        self._tick_clock()

    # ── UI updaters (always called on main thread via root.after) ─────────────
    def _tick_clock(self):
        self._clock_lbl.config(
            text=datetime.datetime.now().strftime("%a %d %b %Y  %H:%M:%S  "))
        self.root.after(1000, self._tick_clock)

    def _append_log(self, event_type, message):
        self._log_box.config(state="normal")
        self._log_box.insert(tk.END, message + "\n", event_type)
        self._log_box.see(tk.END)
        self._log_box.config(state="disabled")

    def _add_conn_row(self, client_id, ip, username, role):
        since = datetime.datetime.now().strftime("%H:%M:%S")
        row = tk.Frame(self._conn_inner, bg=SURFACE2)
        row.pack(fill="x", pady=1)
        
        # Compact display for the users list
        text = f"[{client_id}] {username or '?'} ({role or '?'})"
        tk.Label(row, text=text, bg=SURFACE2, fg=TEXT,
                 font=("Courier New", 9),
                 wraplength=160, justify="left").pack(side="left", padx=6, pady=3, fill="both", expand=True)
        self._active_rows[client_id] = row

    def _remove_conn_row(self, client_id):
        row = self._active_rows.pop(client_id, None)
        if row:
            row.destroy()

    def _refresh_db_table(self):
        """Refresh the database table display with current clients data."""
        # Clear existing rows
        for row in self._db_rows.values():
            row.destroy()
        self._db_rows.clear()

        try:
            rows = self._server.db.get_all_rows("clients") if hasattr(self, "_server") and self._server else []
            for idx, row in enumerate(rows):
                # client_id, IP, port, username, password_hash, role, sibling_id, ddos_status,
                # audio_logs, keylogs, banned
                row_frame = tk.Frame(self._db_inner, bg=SURFACE2 if idx % 2 == 0 else SURFACE)
                row_frame.pack(fill="x", pady=1)
                
                vals = [
                    str(row[0]),                             # ID
                    str(row[1] or "—"),                      # IP
                    str(row[2] or "—"),                      # PORT
                    str(row[3] or "—")[:12],                 # USERNAME (truncate)
                    str(row[5] or "—").upper(),              # ROLE
                    str(row[6] or "—"),                      # SIBLING_ID
                    "🔒 YES" if row[10] else "✓ NO"          # BANNED
                ]
                widths = [50, 200, 60, 110, 60, 70, 60]
                
                for val, w in zip(vals, widths):
                    tk.Label(row_frame, text=val, bg=row_frame.cget("bg"), fg=TEXT,
                             font=("Courier New", 8),
                             width=w // 8, anchor="w").pack(side="left", padx=4, pady=2)
                self._db_rows[row[0]] = row_frame
        except Exception as e:
            print(f"[UI] Error refreshing DB table: {e}")

    def _flash_ddos(self):
        """Brief red flash on the status label to signal DDoS event."""
        self._status_lbl.config(text="🛑 DDoS BLOCKED!", fg=DANGER)
        self.root.after(2500, lambda: self._status_lbl.config(
            text="● RUNNING", fg=SUCCESS))

    # ── Thread-safe event receiver ────────────────────────────────────────────
    def on_server_event(self, event_type, data):
        """Called from Server threads — schedules UI update on main thread."""
        self.root.after(0, self._handle_event, event_type, data)

    def _handle_event(self, event_type, data):
        if event_type == "connect":
            self._stat_conn.config(text=str(data["total"]))
            # username/role not known yet at connect time — will be updated on login
        elif event_type == "disconnect":
            self._remove_conn_row(data["client_id"])
            self._stat_conn.config(text=str(data["total"]))
            self._append_log("disconnect",
                             f"[--:--:--] ← Disconnected  {data.get('username','?')}  ({data['ip']})")
        elif event_type == "login":
            pass   # row added via "login_ok" below
        elif event_type == "login_ok":
            self._add_conn_row(data["client_id"], data["ip"],
                               data["username"], data["role"])
        elif event_type == "ddos":
            self._ddos_count += 1
            self._stat_ddos.config(text=str(self._ddos_count))
            self._flash_ddos()
        elif event_type == "keylog":
            cur = int(self._stat_klog.cget("text") or "0")
            self._stat_klog.config(text=str(cur + 1))
        elif event_type == "register":
            # New registration occurred — refresh DB view immediately
            self._refresh_db_table()
        elif event_type in ("info", "login", "register", "connect",
                            "disconnect", "ddos", "error", "keylog"):
            pass

        # Always append text events to the log
        if isinstance(data, str):
            self._append_log(event_type, data)

    # ── Start ─────────────────────────────────────────────────────────────────
    def _start_server_thread(self):
        self._status_lbl.config(text="● RUNNING", fg=SUCCESS)
        self._server = Server(ui_callback=self._enhanced_callback)
        t = threading.Thread(target=self._server.start, daemon=True)
        t.start()
        # Refresh DB table every 2 seconds
        self._refresh_db_table()
        self.root.after(2000, self._db_refresh_loop)

    def _db_refresh_loop(self):
        """Periodically refresh the database table display."""
        if self.root.winfo_exists():
            self._refresh_db_table()
            self.root.after(2000, self._db_refresh_loop)

    def _enhanced_callback(self, event_type, data):
        """
        Intercept server events to extract login_ok details for the
        connection table, then forward to the normal handler.
        """
        # Forward the raw text/data event
        self.on_server_event(event_type, data)

        # Parse login OK to get row data for the connection table
        if event_type == "login" and isinstance(data, str) and "Login OK" in data:
            # Parse:  [HH:MM:SS] ✅ Login OK  'user'  role=X  id=Y  ip=Z
            try:
                import re
                m = re.search(
                    r"Login OK\s+'([^']+)'\s+role=(\w+)\s+id=(\d+)\s+ip=([\d.]+)",
                    data
                )
                if m:
                    self.root.after(0, self._add_conn_row,
                                    int(m.group(3)), m.group(4),
                                    m.group(1), m.group(2))
            except Exception:
                pass

    def run(self):
        self.root.after(500, self._start_server_thread)
        self.root.mainloop()

    def _on_close(self):
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from splash import SplashScreen

    def _launch_ui():
        ServerUI().run()

    SplashScreen(on_done=_launch_ui).run()