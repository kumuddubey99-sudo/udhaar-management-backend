
import sqlite3
from pathlib import Path


# ---------------------------------------------------------
# DATABASE LOCATION
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ums.db"


# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------

def get_connection():
    connection = sqlite3.connect(DB_PATH)

    # Allows us to access columns by their names
    connection.row_factory = sqlite3.Row

    # Enable foreign-key relationships
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ---------------------------------------------------------
# CREATE DATABASE TABLES
# ---------------------------------------------------------

def init_db():

    connection = get_connection()
    cursor = connection.cursor()

    # =====================================================
    # USERS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('Admin', 'Staff')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # CUSTOMERS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            alternate_phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            address TEXT DEFAULT '',
            performance TEXT DEFAULT 'Average',
            created_date TEXT NOT NULL,
            updated_date TEXT NOT NULL
        )
    """)

    # =====================================================
    # CREDIT TRANSACTIONS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id TEXT PRIMARY KEY,

            customer_id TEXT NOT NULL,

            transaction_date TEXT NOT NULL,

            due_date TEXT NOT NULL,

            amount REAL NOT NULL
                CHECK(amount > 0),

            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending', 'Paid', 'Overdue')),

            notes TEXT DEFAULT '',

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE CASCADE
        )
    """)

    # =====================================================
    # CREDITED ITEMS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credited_items (
            id TEXT PRIMARY KEY,

            transaction_id TEXT NOT NULL,

            item_name TEXT NOT NULL,

            quantity REAL NOT NULL
                CHECK(quantity > 0),

            unit_price REAL NOT NULL
                CHECK(unit_price >= 0),

            subtotal REAL NOT NULL
                CHECK(subtotal >= 0),

            credited_date TEXT NOT NULL,

            FOREIGN KEY(transaction_id)
                REFERENCES credit_transactions(id)
                ON DELETE CASCADE
        )
    """)

    # =====================================================
    # PAYMENTS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,

            customer_id TEXT NOT NULL,

            transaction_id TEXT NOT NULL,

            amount REAL NOT NULL
                CHECK(amount > 0),

            payment_date TEXT NOT NULL,

            payment_method TEXT NOT NULL
                CHECK(
                    payment_method IN
                    ('Cash', 'UPI', 'Bank Transfer', 'Cheque')
                ),

            reference_id TEXT DEFAULT '',

            FOREIGN KEY(customer_id)
                REFERENCES customers(id)
                ON DELETE CASCADE,

            FOREIGN KEY(transaction_id)
                REFERENCES credit_transactions(id)
                ON DELETE CASCADE
        )
    """)

    # =====================================================
    # INDEXES
    # =====================================================

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_transactions_customer
        ON credit_transactions(customer_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_items_transaction
        ON credited_items(transaction_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_payments_customer
        ON payments(customer_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_payments_transaction
        ON payments(transaction_id)
    """)

    # =====================================================
    # DEFAULT LOGIN USERS
    # =====================================================

    cursor.execute("""
        INSERT OR IGNORE INTO users
        (username, password, role)
        VALUES (?, ?, ?)
    """, (
        "admin",
        "admin123",
        "Admin"
    ))

    cursor.execute("""
        INSERT OR IGNORE INTO users
        (username, password, role)
        VALUES (?, ?, ?)
    """, (
        "staff",
        "staff123",
        "Staff"
    ))

    connection.commit()
    connection.close()


# ---------------------------------------------------------
# RUN DATABASE CREATION DIRECTLY
# ---------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("SQLite database created successfully.")
    print(f"Database location: {DB_PATH}")
