#!/usr/bin/env python3
"""Setup the PostgreSQL database for the RAG app."""

import sys
from psycopg import connect
from psycopg.errors import Error as PsycopgError

def test_connection(user, password, dbname="postgres"):
    """Test PostgreSQL connection."""
    try:
        conn = connect(f"host=localhost user={user} password={password} dbname={dbname}")
        conn.close()
        return True
    except Exception as e:
        return False

def setup_database():
    """Set up the database and schema."""
    
    # Test credentials
    credentials = [
        ("postgres", ""),
        ("postgres", "1234"),
        ("postgres", "postgres"),
    ]
    
    admin_user, admin_pass = None, None
    for user, password in credentials:
        if test_connection(user, password):
            admin_user, admin_pass = user, password
            print(f"✓ Connected to PostgreSQL as {user}")
            break
    
    if admin_user is None:
        print("✗ Could not connect to PostgreSQL. Make sure it's running.")
        sys.exit(1)
    
    # Connect as admin and create database
    try:
        admin_conn = connect(f"host=localhost user={admin_user} password={admin_pass} dbname=postgres")
        admin_conn.autocommit = True
        admin_cursor = admin_conn.cursor()
        
        # Enable pgvector extension at template1
        try:
            admin_cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            admin_conn.commit()
            print("✓ pgvector extension enabled")
        except Exception as e:
            print(f"  Note: {e}")
        
        # Create cyberify user if it doesn't exist
        try:
            admin_cursor.execute("SELECT 1 FROM pg_user WHERE usename = 'cyberify'")
            if admin_cursor.fetchone() is None:
                admin_cursor.execute("CREATE USER cyberify WITH PASSWORD '';")
                admin_conn.commit()
                print("✓ User 'cyberify' created")
            else:
                print("✓ User 'cyberify' already exists")
        except Exception as e:
            print(f"  Note creating user: {e}")
        
        # Create database
        try:
            admin_cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'cyberify_rag'")
            if admin_cursor.fetchone() is None:
                admin_cursor.execute("CREATE DATABASE cyberify_rag OWNER cyberify;")
                admin_conn.commit()
                print("✓ Database 'cyberify_rag' created")
            else:
                print("✓ Database 'cyberify_rag' already exists")
                # Grant privileges
                admin_cursor.execute("GRANT ALL PRIVILEGES ON DATABASE cyberify_rag TO cyberify;")
                admin_conn.commit()
        except Exception as e:
            print(f"✗ Error creating database: {e}")
            admin_conn.close()
            sys.exit(1)
        
        admin_conn.close()
    except Exception as e:
        print(f"✗ Admin connection failed: {e}")
        sys.exit(1)
    
    # Now connect to the cyberify_rag database and create schema
    try:
        app_conn = connect(f"host=localhost user={admin_user} password={admin_pass} dbname=cyberify_rag")
        app_cursor = app_conn.cursor()
        
        # Enable pgvector
        try:
            app_cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            app_conn.commit()
            print("✓ pgvector extension enabled in cyberify_rag")
        except Exception as e:
            print(f"  pgvector already exists or error: {e}")
        
        # Load schema
        with open("db/schema.sql", "r") as f:
            schema = f.read()
        
        app_cursor.execute(schema)
        app_conn.commit()
        print("✓ Database schema loaded successfully")
        
        app_conn.close()
    except Exception as e:
        print(f"✗ Error setting up schema: {e}")
        sys.exit(1)
    
    print("\n✓ Database setup complete! Ready to run the app.")

if __name__ == "__main__":
    setup_database()
