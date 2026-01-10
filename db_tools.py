
import mysql.connector
def init():
    mydb = mysql.connector.connect(
        host="localhost",
        user="root",
        password="2wsx3edc4rfv."
    )
    return mydb
  
  
def init_with_db(dbName):
    mydb = mysql.connector.connect(
        host="localhost",
        user="root",
        password="2wsx3edc4rfv.",
        database=dbName
    )
    return mydb  
    
# Function to show the database
def show_databases(mydb):
    mycursor = mydb.cursor()
    mycursor.execute("SHOW DATABASES")
    databases = []
    for i in  mycursor:
        databases.append(i[0])
    return databases


# Function to create a db in the database
def create_database(mydb, dbName):
    
    mycursor = mydb.cursor()
    if dbName not in show_databases(mydb):
        mycursor.execute("CREATE DATABASE " + dbName)

# Function to show tables in the database
def show_tables(mydb):
    
    mycursor = mydb.cursor()
    mycursor.execute("SHOW TABLES")
    tables = []
    for i in  mycursor:
        tables.append(i[0])
    return tables       

# Function to create a table in the database
# Pay Attention: expected format of params is :
#               (name VARCHAR(255), address VARCHAR(255))")
# also NOTICE that you need to have a COUPLE of () around params
def create_table(mydb, tableName, params):
    tables = show_tables(mydb)
    mycursor = mydb.cursor()
    query = "CREATE TABLE " + tableName + " " + params
    print(query)
    if tableName not in  tables:
        mycursor.execute(query)

def delete_table(mydb, tableName):
    tables = show_tables(mydb)
    mycursor = mydb.cursor()
    query = "DROP TABLE " + tableName 
    print(query)
    if tableName in tables:
        mycursor.execute(query)

# TODO show rows of tables

def insert_row(mydb, tableName, columnNames, columnTypes, columnValues):
    mycursor = mydb.cursor()
    tables = show_tables(mydb)
    if tableName in tables:
        sql = "INSERT INTO " + tableName + " "+ columnNames +" VALUES " + columnTypes
        print(sql)
        mycursor.execute(sql, columnValues)
        mydb.commit()
    else:
        print("No table exists with name "+ tableName)

def delete_row(mydb, tableName, columnName, columnValue):
    mycursor = mydb.cursor()
    tables = show_tables(mydb)
    if tableName in tables:
        sql = "DELETE FROM " + tableName + " WHERE "+ columnName + " =  '" + columnValue + "'"
        print(sql)
        mycursor.execute(sql)
        mydb.commit()
    else:
        print("No column name with name "+ tableName)



def get_all_rows(mydb, tableName):
    mycursor = mydb.cursor()
    sql = "SELECT * FROM " + tableName
    mycursor.execute(sql)
    rows = []
    print(mycursor)
    for i in mycursor:
        rows.append(i)
    return rows
    
def get_rows_from_table_with_value(mydb, tableName, columnName, columnValue):
    mycursor = mydb.cursor()
    tables = show_tables(mydb)
    if tableName in tables:
        sql = "SELECT * FROM " + tableName + " WHERE "+ columnName + " =  '" + columnValue + "'"
        print(sql)
        mycursor.execute(sql)
        myresult = mycursor.fetchall()
        return myresult
    else:
        print("No column name with name "+ tableName)

