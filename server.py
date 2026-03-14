# server.py
import socket
import threading
import tools_no_encryption
import os
import datetime
from db_manager import DatabaseManager
from create_tables import create_all_tables
from constants import IP, PORT, MAX_TOTAL_CONNECTIONS, MAX_CONNECTIONS_PER_IP
from encrypt import Encryption
import pygame

# ── Keylog files go into the keylogs/ subfolder ───────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
KEYLOGS_DIR  = os.path.join(_HERE, "keylogs")


class Server:
    def __init__(self):
        self.db = DatabaseManager("localhost", "root", "2wsx3edc4rfv", "project_maria")
        self.encryptor = Encryption()
        self.clients = {}       # client_id -> socket
        self.lock = threading.Lock()
        self.clients_logs = {}  # child_id -> list[str]

        # Connection tracking for DDoS mitigation
        self.ip_connections = {}        # ip (str) -> list[client_id]
        self.active_sockets = {}
        self.total_connections = 0

        # Ensure keylogs directory exists (never deletes it)
        os.makedirs(KEYLOGS_DIR, exist_ok=True)

        try:
            if "clients" not in self.db.show_tables():
                create_all_tables(self.db)
        except Exception:
            create_all_tables(self.db)

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((IP, PORT))
        server_socket.listen()
        print(f"Server listening on {IP}:{PORT}")
        print(f"Limits — Max total: {MAX_TOTAL_CONNECTIONS}, Max per IP: {MAX_CONNECTIONS_PER_IP}")

        while True:
            client_socket, addr = server_socket.accept()
            client_ip = addr[0]
            threading.Thread(
                target=self.handle_client,
                args=(client_socket, client_ip),
                daemon=True
            ).start()

    # ------------------------------------------------------------------
    # Connection-limit helpers
    # ------------------------------------------------------------------

    def _register_connection(self, client_id, client_ip, client_socket):
        """Record a new active connection. Returns True if accepted."""
        with self.lock:
            self.total_connections += 1
            self.ip_connections.setdefault(client_ip, []).append(client_id)
            self.clients[client_id] = client_socket

    def _unregister_connection(self, client_id, client_ip):
        """Remove a connection from tracking."""
        with self.lock:
            if client_id in self.clients:
                del self.clients[client_id]
            if client_ip and client_ip in self.ip_connections:
                try:
                    self.ip_connections[client_ip].remove(client_id)
                except ValueError:
                    pass
                if not self.ip_connections[client_ip]:
                    del self.ip_connections[client_ip]
            if self.total_connections > 0:
                self.total_connections -= 1

    def _check_global_limit(self):
        """Return True if we are AT the global connection limit."""
        with self.lock:
            return self.total_connections >= MAX_TOTAL_CONNECTIONS

    def _check_ip_limit(self, client_ip):
        """Return True if this IP has reached MAX_CONNECTIONS_PER_IP."""
        with self.lock:
            return len(self.ip_connections.get(client_ip, [])) >= MAX_CONNECTIONS_PER_IP

    def _flag_ddos(self, client_ip):
        """
        Set ddos_status=True for all users whose last-known IP matches client_ip,
        disconnect all active connections from that IP, and return their client_ids.
        """
        # Update DB: mark every client from this IP as DDoS
        # We iterate currently tracked IDs for this IP
        with self.lock:
            affected_ids = list(self.ip_connections.get(client_ip, []))

        for cid in affected_ids:
            try:
                self.db.update_row(
                    "clients", "client_id", cid,
                    ["client_ddos_status"], [True]
                )
            except Exception as e:
                print(f"[DDoS] DB update failed for client_id={cid}: {e}")

        # Disconnect every socket from this IP
        with self.lock:
            sockets_to_close = [
                self.clients[cid]
                for cid in affected_ids
                if cid in self.clients
            ]

        for sock in sockets_to_close:
            try:
                sock.close()
            except Exception:
                pass

        print(f"[DDoS] Flagged IP {client_ip} — disconnected {len(affected_ids)} client(s).")
        return affected_ids

    def _is_ddos_flagged(self, username):
        """Return True if the user has ddos_status=True in the DB."""
        try:
            rows = self.db.get_rows_with_value("clients", "client_username", username)
            if rows and rows[0][7]:   # index 7 = client_ddos_status
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Main client handler
    # ------------------------------------------------------------------

    def handle_client(self, client_socket, client_ip):
        client_id = None
        sibling_id = None

        # ── Global connection limit (pre-auth check) ──────────────────
        if self._check_global_limit():
            print(f"[LIMIT] Global limit reached. Rejecting {client_ip}.")
            try:
                self.encryptor.send_encrypted_message(client_socket, "REJECTED|SERVER_FULL")
            except Exception:
                pass
            client_socket.close()
            return

        # ── Per-IP limit (pre-auth check) ─────────────────────────────
        if self._check_ip_limit(client_ip):
            print(f"[DDoS] IP {client_ip} exceeded per-IP limit. Triggering mitigation.")
            try:
                self.encryptor.send_encrypted_message(client_socket, "REJECTED|DDOS_DETECTED")
            except Exception:
                pass
            client_socket.close()
            # Disconnect existing connections from this IP and flag in DB
            self._flag_ddos(client_ip)
            return

        try:
            while True:
                request = self.encryptor.receive_encrypted_message(client_socket)
                if not request:
                    break

                parts = request.split("|")
                command = parts[0]

                # ── LOGIN ─────────────────────────────────────────────
                if command == "LOGIN":
                    username, password = parts[1], parts[2]

                    # Block DDoS-flagged users immediately
                    if self._is_ddos_flagged(username):
                        self.encryptor.send_encrypted_message(
                            client_socket, "LOGIN_FAIL|DDOS_BLOCKED"
                        )
                        print(f"[DDoS] Blocked login attempt by flagged user '{username}'.")
                        break

                    password_hash = tools_no_encryption.get_hash_value(password)
                    users = self.db.get_rows_with_value("clients", "client_username", username)

                    if not users:
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL")
                        continue

                    user = users[0]

                    if user[4] != password_hash:
                        self.encryptor.send_encrypted_message(
                            client_socket, "LOGIN_FAIL|Wrong password"
                        )
                        continue

                    client_id = user[0]
                    role = user[5]
                    sibling_id = user[6]

                    # Store the client IP in DB
                    try:
                        self.db.update_row(
                            "clients", "client_id", client_id,
                            ["client_ip"], [client_ip]
                        )
                    except Exception:
                        pass

                    self._register_connection(client_id, client_ip, client_socket)

                    response = f"LOGIN_OK|{role}|{'CONNECTED' if sibling_id else 'NO_SIBLING'}"
                    self.encryptor.send_encrypted_message(client_socket, response)

                # ── REGISTER ──────────────────────────────────────────
                elif command == "REGISTER":
                    username, password, role = parts[1], parts[2], parts[3].lower()
                    password_hash = tools_no_encryption.get_hash_value(password)

                    p_id = None
                    if role == "child":
                        p_id = int(parts[4])
                        parent_rows = self.db.get_rows_with_value(
                            "clients", "client_id", p_id
                        )
                        if (
                            not parent_rows
                            or parent_rows[0][5] != "parent"
                            or parent_rows[0][6] is not None
                        ):
                            self.encryptor.send_encrypted_message(
                                client_socket, "REGISTER_INVALID_PARENT"
                            )
                            continue

                    new_user_id = self.db.insert_row(
                        "clients",
                        "(client_ip, client_port, client_username, client_password, "
                        "client_role, client_sibling_id, client_ddos_status, "
                        "client_total_audio_logs, client_total_keylogs)",
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (client_ip, None, username, password_hash, role,
                         None, False, 0, 0)
                    )

                    if role == "child" and p_id:
                        self.db.update_row(
                            "clients", "client_id", new_user_id,
                            ["client_sibling_id"], [p_id]
                        )
                        self.db.update_row(
                            "clients", "client_id", p_id,
                            ["client_sibling_id"], [new_user_id]
                        )

                    self.encryptor.send_encrypted_message(
                        client_socket, f"REGISTER_OK|{new_user_id}"
                    )

                # ── FORWARD ───────────────────────────────────────────
                elif command == "FORWARD":
                    payload = request[len("FORWARD|"):]

                    if payload.startswith("KEYLOG_START"):
                        if sibling_id is not None:
                            self.clients_logs[sibling_id] = []

                    elif payload.startswith("KEYLOG_DATA|"):
                        if len(payload.split("|", 1)) > 1:
                            data = payload.split("|", 1)[1]
                            if client_id in self.clients_logs:
                                self.clients_logs[client_id].append(data)

                    elif payload.startswith("KEYLOG_STOP"):
                        if (
                            sibling_id in self.clients_logs
                            and self.clients_logs[sibling_id]
                        ):
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"log_{sibling_id}_{timestamp}.txt"
                            filepath = os.path.join(KEYLOGS_DIR, filename)
                            full_log = "".join(self.clients_logs[sibling_id])

                            with open(filepath, "w", encoding="utf-8", errors="replace") as f:
                                f.write(full_log)

                            self.db.insert_row(
                                "keylogs",
                                "(keylog_parent_id, keylog_child_id, keylog_path_name)",
                                "(%s, %s, %s)",
                                (client_id, sibling_id, filepath)
                            )
                            del self.clients_logs[sibling_id]

                    with self.lock:
                        if sibling_id and sibling_id in self.clients:
                            target_socket = self.clients[sibling_id]
                            self.encryptor.send_encrypted_message(target_socket, payload)

                # ── LOGOUT ────────────────────────────────────────────
                elif command == "LOGOUT":
                    break

        except Exception as e:
            print(f"[Server] Client error ({client_ip}): {type(e).__name__} — {e}")

        finally:
            self._unregister_connection(client_id, client_ip)
            try:
                client_socket.close()
            except Exception:
                pass


if __name__ == "__main__":
    from splash import SplashScreen

    def _start_server():
        Server().start()

    SplashScreen(on_done=_start_server).run()