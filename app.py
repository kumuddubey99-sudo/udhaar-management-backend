
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from database import get_connection, init_db


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="Udhaar Management System",
    description="Backend API for Udhaar Management System",
    version="1.0.0"
)


# =========================================================
# START DATABASE WHEN SERVER STARTS
# =========================================================

@app.on_event("startup")
def startup():

    init_db()

    print("====================================")
    print("Udhaar Management System Backend")
    print("SQLite Database Connected")
    print("====================================")


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def current_date():

    return datetime.now().strftime("%d-%m-%Y")


def row_to_dict(row):

    if row is None:
        return None

    return dict(row)


def generate_id(prefix, table_name):

    connection = get_connection()

    row = connection.execute(
        f"""
        SELECT id
        FROM {table_name}
        ORDER BY rowid DESC
        LIMIT 1
        """
    ).fetchone()

    connection.close()

    if row is None:
        return f"{prefix}001"

    last_id = str(row["id"])

    try:
        number = int(last_id[len(prefix):])
        number += 1

    except (ValueError, TypeError):

        number = 1

    return f"{prefix}{number:03d}"


# =========================================================
# BASIC TEST API
# =========================================================

@app.get("/")
def home():

    return {
        "success": True,
        "message": "Udhaar Management System Backend is running",
        "database": "SQLite"
    }


# =========================================================
# LOGIN MODEL
# =========================================================

class LoginRequest(BaseModel):

    username: str

    password: str

    role: str


# =========================================================
# LOGIN API
# =========================================================

@app.post("/login")
def login(data: LoginRequest):

    connection = get_connection()

    user = connection.execute(
        """
        SELECT
            id,
            username,
            role
        FROM users
        WHERE username = ?
        AND password = ?
        AND role = ?
        """,
        (
            data.username,
            data.password,
            data.role
        )
    ).fetchone()

    connection.close()

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid username, password or role"
        )

    return {
        "success": True,
        "message": "Login successful",
        "user": row_to_dict(user)
    }


# =========================================================
# CUSTOMER MODEL
# =========================================================

class CustomerCreate(BaseModel):

    name: str

    phone: str

    alternate_phone: str = ""

    email: str = ""

    address: str = ""

    performance: str = "Average"


# =========================================================
# ADD CUSTOMER
# =========================================================

@app.post("/customers")
def add_customer(data: CustomerCreate):

    customer_id = generate_id(
        "C",
        "customers"
    )

    date = current_date()

    connection = get_connection()

    connection.execute(
        """
        INSERT INTO customers
        (
            id,
            name,
            phone,
            alternate_phone,
            email,
            address,
            performance,
            created_date,
            updated_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            data.name,
            data.phone,
            data.alternate_phone,
            data.email,
            data.address,
            data.performance,
            date,
            date
        )
    )

    connection.commit()

    customer = connection.execute(
        """
        SELECT *
        FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()

    connection.close()

    return {
        "success": True,
        "message": "Customer added successfully",
        "customer": row_to_dict(customer)
    }


# =========================================================
# GET ALL CUSTOMERS
# =========================================================

@app.get("/customers")
def get_customers():

    connection = get_connection()

    customers = connection.execute(
        """
        SELECT *
        FROM customers
        ORDER BY rowid DESC
        """
    ).fetchall()

    connection.close()

    return {
        "success": True,
        "customers": [
            dict(customer)
            for customer in customers
        ]
    }


# =========================================================
# GET SINGLE CUSTOMER
# =========================================================

@app.get("/customers/{customer_id}")
def get_customer(customer_id: str):

    connection = get_connection()

    customer = connection.execute(
        """
        SELECT *
        FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()

    connection.close()

    if customer is None:

        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    return {
        "success": True,
        "customer": row_to_dict(customer)
    }


# =========================================================
# UPDATE CUSTOMER
# =========================================================

@app.put("/customers/{customer_id}")
def update_customer(
    customer_id: str,
    data: CustomerCreate
):

    connection = get_connection()

    existing = connection.execute(
        """
        SELECT id
        FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()

    if existing is None:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    connection.execute(
        """
        UPDATE customers
        SET
            name = ?,
            phone = ?,
            alternate_phone = ?,
            email = ?,
            address = ?,
            performance = ?,
            updated_date = ?
        WHERE id = ?
        """,
        (
            data.name,
            data.phone,
            data.alternate_phone,
            data.email,
            data.address,
            data.performance,
            current_date(),
            customer_id
        )
    )

    connection.commit()

    customer = connection.execute(
        """
        SELECT *
        FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    ).fetchone()

    connection.close()

    return {
        "success": True,
        "message": "Customer updated successfully",
        "customer": row_to_dict(customer)
    }


# =========================================================
# DELETE CUSTOMER
# =========================================================

@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: str):

    connection = get_connection()

    result = connection.execute(
        """
        DELETE FROM customers
        WHERE id = ?
        """,
        (customer_id,)
    )

    connection.commit()

    connection.close()

    if result.rowcount == 0:

        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    return {
        "success": True,
        "message": "Customer deleted successfully"
    }

