# constants.py
# This file contains constants used across the application.

CHUNK_SIZE = 4096
SERVER_BIND_IP = "0.0.0.0"  # Server listens on all network interfaces
SERVER_IP = "192.168.68.100"  # Client should connect to this server LAN address
PORT = 9921
DB_NAME = "MySQL_GurAvidar"
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "2wsx3edc4rfv",
    "database": DB_NAME
}

# Connection limits
MAX_TOTAL_CONNECTIONS = 15
MAX_CONNECTIONS_PER_IP = 3