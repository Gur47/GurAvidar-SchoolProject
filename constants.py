# constants.py
# This file contains constants used across the application.

CHUNK_SIZE = 4096
IP = "127.0.0.1"
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