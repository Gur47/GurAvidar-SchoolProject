import socket
import tkinter as tk
from tkinter import messagebox
from encrypt import Encryption
from constants import IP, PORT

class Client:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.encryptor = Encryption()
        self.connected = False

    def connect(self):
        try:
            self.sock.connect((IP, PORT))
            self.connected = True
        except Exception as e:
            messagebox.showerror("error", f"cannot connect to server: {e}")

    def send(self, message: str):
        if self.connected:
            self.encryptor.send_encrypted_message(self.sock, message)

    def receive(self) -> str:
        if self.connected:
            return self.encryptor.receive_encrypted_message(self.sock)
        return ""

    def close(self):
        if self.connected:
            self.sock.close()
            self.connected = False


class ClientGUI:
    def __init__(self):
        self.client = Client()
        self.client.connect()

        self.root = tk.Tk()
        self.root.title("Parental Control")
        self.root.geometry("400x350")
        self.build_login_screen()

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # ---------- login ----------
    def build_login_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Login", font=("Arial", 16)).pack(pady=10)
        tk.Label(self.root, text="Username").pack()
        self.username_entry = tk.Entry(self.root)
        self.username_entry.pack()
        tk.Label(self.root, text="Password").pack()
        self.password_entry = tk.Entry(self.root, show="*")
        self.password_entry.pack()
        tk.Button(self.root, text="Login", command=self.login).pack(pady=10)
        tk.Button(self.root, text="Press here to register", fg="blue", command=self.build_register_screen).pack()

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        if not username or not password:
            messagebox.showerror("error", "fill all fields")
            return
        self.client.send(f"LOGIN|{username}|{password}")
        response = self.client.receive()
        
        if response.startswith("LOGIN_OK"):
            parts = response.split("|")
            role = parts[1]
            sibling_status = parts[2] # "CONNECTED" או "NO_SIBLING"
            
            if role == "parent":
                if sibling_status == "NO_SIBLING":
                    messagebox.showinfo("info", "Welcome! Please link a child using your ID.")
                self.build_parent_screen()
            else:
                if sibling_status == "NO_SIBLING":
                    messagebox.showerror("error", "Child account not linked properly.")
                    return
                self.build_child_screen()
        else:
            messagebox.showerror("error", "Login failed: check username/password")

    # ---------- register ----------
    def build_register_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Register", font=("Arial", 16)).pack(pady=10)
        tk.Label(self.root, text="Username").pack()
        self.reg_username = tk.Entry(self.root)
        self.reg_username.pack()
        tk.Label(self.root, text="Password").pack()
        self.reg_password = tk.Entry(self.root, show="*")
        self.reg_password.pack()
        tk.Label(self.root, text="Role").pack()
        self.role_var = tk.StringVar(value="parent")
        tk.Radiobutton(self.root, text="parent", variable=self.role_var, value="parent").pack()
        tk.Radiobutton(self.root, text="child", variable=self.role_var, value="child").pack()
        tk.Label(self.root, text="Parent ID (if child)").pack()
        self.parent_id_entry = tk.Entry(self.root)
        self.parent_id_entry.pack()
        tk.Button(self.root, text="Register", command=self.register).pack(pady=10)
        tk.Button(self.root, text="Back", command=self.build_login_screen).pack()

    def register(self):
        username = self.reg_username.get()
        password = self.reg_password.get()
        role = self.role_var.get()
        
        if role == "child":
            parent_id = self.parent_id_entry.get()
            if not parent_id.isdigit():
                messagebox.showerror("error", "Please enter a valid Parent ID")
                return
            msg = f"REGISTER|{username}|{password}|{role}|{parent_id}"
        else:
            msg = f"REGISTER|{username}|{password}|{role}"
            
        self.client.send(msg)
        response = self.client.receive()
        
        if response.startswith("REGISTER_OK"):
            new_id = response.split("|")[1]
            messagebox.showinfo("Success", f"Registered successfully!\nYour ID is: {new_id}\nUse this ID to link your child.")
            self.build_login_screen()
        elif "REGISTER_PARENT_NOT_FOUND" in response:
            messagebox.showerror("error", "Parent ID not found in system")
        elif "REGISTER_PARENT_BUSY" in response:
            messagebox.showerror("error", "This parent already has a child linked")
        else:
            messagebox.showerror("error", "Registration failed")

    # ---------- parent screen ----------
    def build_parent_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Parent Control Panel", font=("Arial", 16)).pack(pady=10)
        tk.Button(self.root, text="Start screen share", command=lambda: self.client.send("SCREEN_START")).pack(pady=5)
        tk.Button(self.root, text="Start keylogger", command=lambda: self.client.send("KEYLOG_START")).pack(pady=5)
        tk.Button(self.root, text="Logout", command=self.logout).pack(pady=10)

    # ---------- child screen ----------
    def build_child_screen(self):
        self.clear_screen()
        tk.Label(self.root, text="Child Connected", font=("Arial", 16)).pack(pady=40)
        tk.Label(self.root, text="Waiting for parent commands").pack()
        tk.Button(self.root, text="Logout", command=self.logout).pack(pady=10)

    def logout(self):
        self.client.send("LOGOUT")
        self.client.close()
        self.root.destroy()


if __name__ == "__main__":
    app = ClientGUI()
    app.root.mainloop()
