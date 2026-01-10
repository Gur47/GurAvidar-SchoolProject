import socket
import threading
from db_manager import DatabaseManager
from create_tables import create_all_tables
from constants import IP, PORT
from encrypt import Encryption
import tools_no_encryption

class Server:
    def __init__(self):
        self.db = DatabaseManager("localhost", "root", "2wsx3edc4rfv", "project_maria")
        self.encryptor = Encryption()
        self.clients = {} 
        self.lock = threading.Lock()

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
        try:
            while True:
                request = self.encryptor.receive_encrypted_message(client_socket)
                if not request: break
                
                parts = request.split("|")
                command = parts[0]

                if command == "LOGIN":
                    username, password = parts[1], parts[2]
                    password_hash = tools_no_encryption.get_hash_value(password)
                    user = self.db.get_rows_with_value("clients", "client_username", username)

                    if not user or user[0][4] != password_hash:
                        self.encryptor.send_encrypted_message(client_socket, "LOGIN_FAIL")
                        continue

                    client_id = user[0][0]
                    role = user[0][5]
                    sibling_id = user[0][6]

                    # עדכון IP ופורט נוכחיים
                    ip, port = client_socket.getpeername()
                    self.db.update_row("clients", "client_id", client_id, ["client_ip", "client_port"], [ip, port])

                    with self.lock:
                        self.clients[client_id] = client_socket

                    # הורה יכול להתחבר גם אם אין לו ילד עדיין, פשוט נשלח סטטוס מתאים
                    if sibling_id is None:
                        response = f"LOGIN_OK|{role}|NO_SIBLING"
                    else:
                        response = f"LOGIN_OK|{role}|CONNECTED"
                    
                    self.encryptor.send_encrypted_message(client_socket, response)

                elif command == "REGISTER":
                    username, password, role = parts[1], parts[2], parts[3].lower()
                    password_hash = tools_no_encryption.get_hash_value(password)
                    
                    # 1. בדיקה מוקדמת אם מדובר בילד - האם האבא קיים ופנוי?
                    parent_id = None
                    if role == "child":
                        parent_id = int(parts[4])
                        # בדיקה שהאבא קיים והוא אכן הורה ללא ילד אחר
                        parent_rows = self.db.get_rows_with_value("clients", "client_id", parent_id)
                        if not parent_rows:
                            self.encryptor.send_encrypted_message(client_socket, "REGISTER_PARENT_NOT_FOUND")
                            continue
                        
                        parent_data = parent_rows[0] # (id, ip, port, user, pass, role, sibling_id...)
                        if parent_data[5] != "parent":
                            self.encryptor.send_encrypted_message(client_socket, "REGISTER_INVALID_PARENT")
                            continue
                        if parent_data[6] is not None: # sibling_id של האבא כבר תפוס
                            self.encryptor.send_encrypted_message(client_socket, "REGISTER_PARENT_BUSY")
                            continue

                    # 2. יצירת המשתמש החדש בטבלה
                    new_user_id = self.db.insert_row(
                        "clients",
                        "(client_ip, client_port, client_username, client_password, client_role, client_sibling_id, client_ddos_status, client_total_audio_logs, client_total_keylogs)",
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (None, None, username, password_hash, role, None, False, 0, 0)
                    )

                    # 3. ביצוע הקישור (רק אם מדובר בילד והרישום הצליח)
                    if role == "child" and new_user_id and parent_id:
                        print(f"Linking Child {new_user_id} with Parent {parent_id}...")
                        
                        # עדכון שורת הילד - שישים את ה-ID של האבא ב-sibling_id
                        self.db.update_row("clients", "client_id", new_user_id, ["client_sibling_id"], [parent_id])
                        
                        # עדכון שורת האבא - שישים את ה-ID של הילד ב-sibling_id
                        self.db.update_row("clients", "client_id", parent_id, ["client_sibling_id"], [new_user_id])
                        
                        print("Bidirectional link established successfully.")

                    # 4. אישור ללקוח
                    self.encryptor.send_encrypted_message(client_socket, f"REGISTER_OK|{new_user_id}")

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