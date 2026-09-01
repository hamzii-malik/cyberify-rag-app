#!/usr/bin/env python3
"""Set password for cyberify database user."""

from psycopg import connect

try:
    # Connect as postgres
    conn = connect("host=localhost user=postgres password= dbname=postgres")
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Set password for cyberify user
    cursor.execute("ALTER USER cyberify WITH PASSWORD 'cyberify123';")
    print("✓ Password set for cyberify user")
    
    conn.close()
except Exception as e:
    print(f"✗ Error: {e}")
