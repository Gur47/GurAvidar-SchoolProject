# create_tables.py
from db_manager import DatabaseManager

def create_all_tables(db):
    # clients table
    db.create_table(
        "clients",
        "("
        "client_id INT AUTO_INCREMENT PRIMARY KEY, "
        "client_ip VARCHAR(255), "
        "client_port INT, "
        "client_username VARCHAR(255), "
        "client_password VARCHAR(255), "
        "client_role VARCHAR(10), "
        "client_sibling_id INT, "
        "client_ddos_status BOOLEAN, "
        "client_total_audio_logs INT, "
        "client_total_keylogs INT, "
        "client_ip_banned BOOLEAN DEFAULT FALSE, "
        "client_2fa_enabled BOOLEAN DEFAULT FALSE, "
        "client_2fa_secret VARCHAR(255)"
        ")"
    )

    # keylogs table
    db.create_table(
        "keylogs",
        "("
        "keylog_id INT AUTO_INCREMENT PRIMARY KEY, "
        "keylog_parent_id INT, "
        "keylog_child_id INT, "
        "keylog_path_name VARCHAR(255)"
        ")"
    )

