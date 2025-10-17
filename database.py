import sqlite3

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users
        (user_id INTEGER PRIMARY KEY, api_key TEXT)
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
