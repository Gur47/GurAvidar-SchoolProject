# db_manager.py
# This file manages all interactions with the database using a class-based approach.

from datetime import datetime
from mysql.connector import connect

class DatabaseManager:
    def __init__(self, host, user, password, database=None):
        """
        Initialize the DatabaseManager with connection parameters.
        
        Args:
            host: Database host address
            user: Database username
            password: Database password
            database: Optional database name to connect to
        """
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.conn = None
        self._connect()
    
    def _connect(self):
        """Establish connection to the database"""
        if self.database:
            self.conn = connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
        else:
            self.conn = connect(
                host=self.host,
                user=self.user,
                password=self.password
            )
    
    def reconnect(self, database=None):
        """
        Reconnect to the database, optionally with a different database name
        
        Args:
            database: Optional new database to connect to
        """
        if self.conn:
            self.conn.close()
        
        if database:
            self.database = database
        
        self._connect()
    
    def show_databases(self):
        """Return a list of all databases"""
        cursor = self.conn.cursor()
        cursor.execute("SHOW DATABASES")
        return [db[0] for db in cursor]
    
    def create_database(self, db_name):
        """Create a new database if it doesn't exist"""
        if db_name not in self.show_databases():
            cursor = self.conn.cursor()
            cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"Database {db_name} created successfully.")
    
    def show_tables(self):
        """Return a list of all tables in the current database"""
        if not self.database:
            raise ValueError("No database selected.")
        
        cursor = self.conn.cursor()
        cursor.execute("SHOW TABLES")
        return [table[0] for table in cursor]
    
    def create_table(self, table_name, params):
        """
        Create a new table if it doesn't exist
        
        Args:
            table_name: Name of the table to create
            params: SQL parameters for table creation
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if table_name not in tables:
            cursor = self.conn.cursor()
            query = f"CREATE TABLE {table_name} {params}"
            cursor.execute(query)
            self.conn.commit()
            print(f"Table {table_name} created successfully.")
    
    def delete_table(self, table_name):
        """Drop a table if it exists"""
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if table_name in tables:
            cursor = self.conn.cursor()
            cursor.execute(f"DROP TABLE {table_name}")
            self.conn.commit()
            print(f"Table {table_name} deleted successfully.")
        else:
            print(f"Table {table_name} does not exist.")
    
    def insert_row(self, table_name, column_names, column_types, column_values):
        """
        Insert a row into a table
        
        Args:
            table_name: Name of the target table
            column_names: Column names formatted as SQL string
            column_types: Column types formatted as SQL string
            column_values: Values to insert
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if table_name in tables:
            cursor = self.conn.cursor()
            query = f"INSERT INTO {table_name} {column_names} VALUES {column_types}"
            cursor.execute(query, column_values)
            self.conn.commit()
            last_id = cursor.lastrowid
            print(f"Successfully inserted into {table_name}, Generated ID: {last_id}")
            #print(f"Row inserted into table {table_name} successfully.")
            return last_id  # מחזיר את ה-ID של השורה שהוכנסה
        else:
            #print(f"Table {table_name} does not exist.")
            return None
    
    def delete_row(self, table_name, column_name, column_value):
        """
        Delete a row from a table based on a column value
        
        Args:
            table_name: Name of the target table
            column_name: Column to filter on
            column_value: Value to match for deletion
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if table_name in tables:
            cursor = self.conn.cursor()
            query = f"DELETE FROM {table_name} WHERE {column_name} = '{column_value}'"
            cursor.execute(query)
            self.conn.commit()
            print(f"Row deleted from table {table_name} successfully.")
        else:
            print(f"Table {table_name} does not exist.")
    
    def get_all_rows(self, table_name):
        """
        Get all rows from a table
        
        Args:
            table_name: Name of the target table
            
        Returns:
            List of all rows in the table
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        return cursor.fetchall()
    
    def get_rows_with_value(self, table_name, column_name, column_value):
        """
        Get rows from a table where a column matches a value
        
        Args:
            table_name: Name of the target table
            column_name: Column to filter on
            column_value: Value to match
            
        Returns:
            List of matching rows
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if table_name in tables:
            cursor = self.conn.cursor()
            query = f"SELECT * FROM {table_name} WHERE {column_name} = '{column_value}'"
            cursor.execute(query)
            return cursor.fetchall()
        else:
            print(f"Table {table_name} does not exist.")
            return []
    
    def update_row(self, table_name, primary_key_column, primary_key_value, column_names, column_values):
        """
        Update a row in a table
        
        Args:
            table_name: Name of the target table
            primary_key_column: Primary key column name
            primary_key_value: Primary key value to match
            column_names: List of column names to update
            column_values: List of new values
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if table_name in tables:
            cursor = self.conn.cursor()
            set_clause = ", ".join(f"{col} = %s" for col in column_names)
            query = f"UPDATE {table_name} SET {set_clause} WHERE {primary_key_column} = %s"
            values = column_values + [primary_key_value]
            cursor.execute(query, values)
            self.conn.commit()
            print(f"Row in table {table_name} updated successfully.")
        else:
            print(f"Table {table_name} does not exist.")
    
    def insert_decrypted_media(self, user_id, media_type_id, path):
        """
        Insert a record into the `decrypted_media` table.
        
        Args:
            user_id: ID of the user
            media_type_id: Type of media (e.g., 1 for image, 2 for video, 3 for audio)
            path: Path to the decrypted media
        """
        if not self.database:
            raise ValueError("No database selected.")
            
        tables = self.show_tables()
        if "decrypted_media" in tables:
            cursor = self.conn.cursor()
            query = """
                INSERT INTO decrypted_media (user_id, media_type_id, path_to_decrypted_media)
                VALUES (%s, %s, %s)
            """
            cursor.execute(query, (user_id, media_type_id, path))
            self.conn.commit()
            print(f"Media record inserted: User ID={user_id}, Media Type={media_type_id}, Path={path}")
        else:
            print("Table `decrypted_media` does not exist.")
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            print("Database connection closed.")