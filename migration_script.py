"""
Database migration script to add the required columns for admin dashboard

This script adds:
- is_active column to User model
- last_login column to User model
- ApiKey table
- ApiUsage table
"""

import sqlite3
import os
from datetime import datetime

def run_migration():
    # Path to the database file
    db_path = 'tryontrend.db'
    
    # Full path with the current directory
    full_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)
    
    print(f"Running migration on database: {full_db_path}")
    
    # Connect to the database
    conn = sqlite3.connect(full_db_path)
    cursor = conn.cursor()
    
    # Start a transaction
    conn.execute('BEGIN TRANSACTION')
    
    try:
        # Check if is_active column exists in the user table
        cursor.execute("PRAGMA table_info(user)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add is_active column if it doesn't exist
        if 'is_active' not in columns:
            print("Adding is_active column to user table...")
            cursor.execute("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1")
        else:
            print("is_active column already exists in user table")
        
        # Add last_login column if it doesn't exist
        if 'last_login' not in columns:
            print("Adding last_login column to user table...")
            cursor.execute("ALTER TABLE user ADD COLUMN last_login TIMESTAMP")
        else:
            print("last_login column already exists in user table")
        
        # Create ApiKey table if it doesn't exist
        print("Creating ApiKey table if it doesn't exist...")
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_key (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER NOT NULL,
            last_used TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES user (id)
        )
        ''')
        
        # Create ApiUsage table if it doesn't exist
        print("Creating ApiUsage table if it doesn't exist...")
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            user_id INTEGER,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            response_time INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            FOREIGN KEY (api_key_id) REFERENCES api_key (id),
            FOREIGN KEY (user_id) REFERENCES user (id)
        )
        ''')
        
        # Commit the transaction
        conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        print(f"Error during migration: {e}")
        raise
    
    finally:
        # Close the connection
        conn.close()

if __name__ == "__main__":
    run_migration()