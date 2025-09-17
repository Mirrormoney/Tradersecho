import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "app.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL)")
        conn.commit()

def get_user_by_username(username: str):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT username, password_hash FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        if row:
            return {"username": row[0], "password_hash": row[1]}
        return None

def create_user(username: str, password_hash: str):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        conn.commit()