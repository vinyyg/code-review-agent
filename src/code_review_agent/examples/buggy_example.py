import os
import json
import requests

SECRET_KEY = "sk-prod-abc123xyz789"

def get_user(user_id):
    import sqlite3
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")
    return cursor.fetchone()

def process_data(data):
    result = eval(data)
    return result

def calculate(x):
    if x > 0:
        if x > 10:
            if x > 100:
                if x > 1000:
                    return x * 3.14159
                else:
                    return x * 2.71828
            else:
                return x * 1.41421
        else:
            return x * 1.73205
    else:
        return 0

def unused_function():
    y = 42
    return None

class UserManager:
    def create_user(self, name, email, password, role, department, address, phone):
        import hashlib
        hashed = hashlib.md5(password.encode()).hexdigest()
        self.save_to_db(name, email, hashed, role, department, address, phone)
        self.send_welcome_email(email)
        self.log_creation(name, email)
        self.notify_admin(name, role)
        self.update_stats()