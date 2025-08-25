#!/usr/bin/env python3

import sqlite3
import uuid
import sys
import os

# Add the current directory to Python path to import from app.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATABASE = 'database.db'

def migrate_secure_tokens():
    """Add secure_token column to groups table and populate it for existing groups"""
    
    print("Starting secure token migration...")
    
    if not os.path.exists(DATABASE):
        print(f"Database file {DATABASE} not found. Please run the main application first.")
        return
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    
    try:
        # Check if groups table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='groups'")
        if not cursor.fetchone():
            print("Groups table not found. Nothing to migrate.")
            conn.close()
            return
        
        # Check if secure_token column already exists
        cursor = conn.execute("PRAGMA table_info(groups)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'secure_token' in columns:
            print("secure_token column already exists.")
        else:
            print("Adding secure_token column to groups table...")
            conn.execute("ALTER TABLE groups ADD COLUMN secure_token TEXT")
            print("✓ Column added successfully.")
        
        # Generate tokens for groups that don't have them
        groups_needing_tokens = conn.execute('SELECT id, name FROM groups WHERE secure_token IS NULL OR secure_token = ""').fetchall()
        
        if not groups_needing_tokens:
            print("All groups already have secure tokens.")
        else:
            print(f"Generating tokens for {len(groups_needing_tokens)} groups...")
            
            for group in groups_needing_tokens:
                token = str(uuid.uuid4())
                conn.execute('UPDATE groups SET secure_token = ? WHERE id = ?', (token, group['id']))
                print(f"✓ Generated token for group '{group['name']}' (ID: {group['id']}): {token}")
        
        # Create unique index for security (if it doesn't exist)
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_secure_token ON groups(secure_token)")
            print("✓ Created unique index on secure_token column.")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not create unique index: {e}")
        
        # Commit all changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Show final status
        all_groups = conn.execute('SELECT id, name, secure_token FROM groups').fetchall()
        if all_groups:
            print(f"\nFinal status - {len(all_groups)} groups with secure tokens:")
            for group in all_groups:
                print(f"  - {group['name']} (ID: {group['id']}): {group['secure_token'][:8]}...")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_secure_tokens()
