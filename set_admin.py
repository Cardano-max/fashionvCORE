# This script directly updates or creates an admin account with specific credentials
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

# Path to the database
db_path = 'tryontrend.db'
full_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)

# Admin credentials
admin_email = "Shahkaushal26@gmail.com"
admin_password = "admintryontrend@123"
admin_username = "admin"
password_hash = generate_password_hash(admin_password)
is_admin = 1  # True in SQLite
created_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
credits = 10

# Connect to the database
conn = sqlite3.connect(full_db_path)
cursor = conn.cursor()

try:
    # Check if user exists
    cursor.execute("SELECT id FROM user WHERE email = ?", (admin_email,))
    user = cursor.fetchone()
    
    if user:
        # Update existing user
        user_id = user[0]
        print(f"Updating existing user ID {user_id} with new admin credentials")
        cursor.execute(
            "UPDATE user SET username = ?, password_hash = ?, is_admin = ?, credits = ? WHERE id = ?",
            (admin_username, password_hash, is_admin, credits, user_id)
        )
    else:
        # Create new admin user
        print(f"Creating new admin user with email {admin_email}")
        cursor.execute(
            "INSERT INTO user (username, email, password_hash, is_admin, created_at, credits) VALUES (?, ?, ?, ?, ?, ?)",
            (admin_username, admin_email, password_hash, is_admin, created_at, credits)
        )
    
    # Commit changes
    conn.commit()
    print("Admin credentials set successfully!")
    
except Exception as e:
    conn.rollback()
    print(f"Error setting admin credentials: {str(e)}")
    
finally:
    conn.close()
