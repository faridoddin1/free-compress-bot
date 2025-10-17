import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users
        (user_id INTEGER PRIMARY KEY, api_key TEXT)
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS compressed_files
        (file_id INTEGER PRIMARY KEY AUTOINCREMENT,
         user_id INTEGER,
         original_file_name TEXT,
         compressed_file_name TEXT,
         compressed_date TEXT)
    ''')
    conn.commit()
    conn.close()

def set_api_key(user_id, api_key):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, api_key) VALUES (?, ?)", (user_id, api_key))
    conn.commit()
    conn.close()

def get_api_key(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT api_key FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    return None

def add_compressed_file(user_id, original_file_name, compressed_file_name):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    compressed_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO compressed_files (user_id, original_file_name, compressed_file_name, compressed_date) VALUES (?, ?, ?, ?)",
              (user_id, original_file_name, compressed_file_name, compressed_date))
    conn.commit()
    conn.close()

def get_user_files(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT file_id, original_file_name, compressed_file_name, compressed_date FROM compressed_files WHERE user_id=?", (user_id,))
    results = c.fetchall()
    conn.close()
    return results

def delete_compressed_file(file_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("DELETE FROM compressed_files WHERE file_id=?", (file_id,))
    conn.commit()
    conn.close()
