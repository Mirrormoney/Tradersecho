from db import SessionLocal, get_user_by_username, create_user
from auth import get_password_hash
def ensure_user(username, password, pro=False):
    with SessionLocal() as db:
        if get_user_by_username(db, username):
            print(f"User {username} exists"); return
        hashed = get_password_hash(password)
        create_user(db, username, hashed, pro=pro)
        print(f"Created {username} (pro={pro})")
if __name__ == "__main__":
    ensure_user("admin@example.com", "admin123", pro=True)
    ensure_user("user@example.com", "user123", pro=False)