import mysql.connector
import sqlite3
import os
import yaml

# Read config
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

# Connect to MySQL
print("Connecting to local MySQL database...")
try:
    mysql_conn = mysql.connector.connect(**config['mysql'])
    mysql_cursor = mysql_conn.cursor()
except Exception as err:
    print(f"Error connecting to MySQL: {err}")
    print("Please make sure MySQL is running and credentials in config/config.yaml are correct.")
    exit(1)

# Ensure data dir exists
os.makedirs("data", exist_ok=True)
sqlite_path = "data/stock_cache.db"
print(f"Initializing SQLite database cache at: {sqlite_path}")
sqlite_conn = sqlite3.connect(sqlite_path)
sqlite_cursor = sqlite_conn.cursor()

# Create SQLite tables if not exists
sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS indices (
        index_name TEXT PRIMARY KEY,
        csv_url TEXT NOT NULL,
        last_updated TEXT
    );
""")
sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS index_constituents (
        index_name TEXT,
        symbol TEXT,
        PRIMARY KEY (index_name, symbol)
    );
""")
sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_data (
        symbol TEXT,
        date TEXT,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        PRIMARY KEY (symbol, date)
    );
""")
sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS fundamentals (
        symbol TEXT PRIMARY KEY,
        last_updated TEXT,
        data_json TEXT
    );
""")
sqlite_conn.commit()

# Helper to copy table
def copy_table(table_name, select_cols, insert_placeholders):
    mysql_cursor.execute(f"SELECT {select_cols} FROM {table_name}")
    rows = mysql_cursor.fetchall()
    print(f"Copying {len(rows)} rows from MySQL '{table_name}' to SQLite...")
    
    from decimal import Decimal
    from datetime import datetime, date
    cleaned_rows = []
    for r in rows:
        cleaned_row = []
        for val in r:
            if isinstance(val, Decimal):
                cleaned_row.append(float(val))
            elif isinstance(val, (datetime, date)):
                cleaned_row.append(val.strftime('%Y-%m-%d %H:%M:%S') if isinstance(val, datetime) else val.strftime('%Y-%m-%d'))
            else:
                cleaned_row.append(val)
        cleaned_rows.append(tuple(cleaned_row))
    
    # We use INSERT OR REPLACE to keep SQLite tables clean
    insert_query = f"INSERT OR REPLACE INTO {table_name} ({select_cols}) VALUES ({insert_placeholders})"
    
    # Batch insert
    sqlite_cursor.executemany(insert_query, cleaned_rows)
    sqlite_conn.commit()

try:
    copy_table("indices", "index_name, csv_url, last_updated", "?, ?, ?")
    copy_table("index_constituents", "index_name, symbol", "?, ?")
    copy_table("price_data", "symbol, date, open, high, low, close, volume", "?, ?, ?, ?, ?, ?, ?")
    copy_table("fundamentals", "symbol, last_updated, data_json", "?, ?, ?")
    print("\nSuccess! Database migration completed successfully.")
    print("Now you can commit 'data/stock_cache.db' to your git repository.")
except Exception as e:
    print(f"Error migrating data: {e}")
finally:
    mysql_cursor.close()
    mysql_conn.close()
    sqlite_cursor.close()
    sqlite_conn.close()
