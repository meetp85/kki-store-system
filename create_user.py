"""
Run this on YOUR computer (not on Render) to create or update a login account
for the KKI Store app. It connects straight to your Aiven MySQL database.

Usage:
    python create_user.py

You'll be prompted for your Aiven connection details (once) and the new
username/password to create. Run it again anytime to add more team members
or reset a password.
"""
import getpass
import os

import pymysql
from werkzeug.security import generate_password_hash

host = os.environ.get("MYSQL_HOST") or input("MySQL Host (from Aiven): ").strip()
port = int(os.environ.get("MYSQL_PORT") or input("MySQL Port (from Aiven): ").strip())
user = os.environ.get("MYSQL_USER") or input("MySQL User (from Aiven, e.g. avnadmin): ").strip()
password = os.environ.get("MYSQL_PASSWORD") or getpass.getpass("MySQL Password (from Aiven): ")
database = os.environ.get("MYSQL_DATABASE") or input("MySQL Database name (from Aiven, e.g. defaultdb): ").strip()

conn = pymysql.connect(
    host=host, port=port, user=user, password=password, database=database,
    ssl={"ssl": {}},
)
try:
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL
            )"""
        )

    new_username = input("\nNew login username (e.g. store, production): ").strip()
    new_password = getpass.getpass("New login password: ")
    pw_hash = generate_password_hash(new_password)

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users (username, password_hash) VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE password_hash=%s""",
            (new_username, pw_hash, pw_hash),
        )
    conn.commit()
    print(f'\n✅ User "{new_username}" created/updated. They can now log in on the site.')
finally:
    conn.close()
