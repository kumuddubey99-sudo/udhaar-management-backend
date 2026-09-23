from datetime import datetime, date
from typing import Optional
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import get_connection, init_db


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="Udhaar Management System",
    description="Complete backend API for the Udhaar Management System",
    version="2.0.0",
)

# Needed when the Flet UI is eventually opened from a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup():
    init_db()
    print("====================================")
    print("Udhaar Management System Backend")
    print("SQLite Database Connected")
    print("====================================")


# =========================================================
# COMMON HELPERS
# =========================================================

def today_ddmmyyyy():
    return datetime.now().strftime("%d-%m-%Y")


def today_iso():
    return datetime.now().strftime("%Y-%m-%d")


def row_to_dict(row):
    return dict(row) if row is not None else None


def parse_date(value: str):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def normalize_date(value: str, field_name: str):
    parsed = parse_date(value)
    if parsed is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Use YYYY-MM-DD or DD-MM-YYYY."
        )
    return value


def next_id(connection, table_name: str, column_name: str, prefix: str):
    row = connection.execute(
        f"SELECT {column_name} FROM {table_name} ORDER BY rowid DESC LIMIT 1"
    ).fetchone()

    if row is None:
        return f"{prefix}001"

    last_id = str(row[column_name])
    try:
        number = int(last_id[len(prefix):]) + 1
    except (ValueError, TypeError):
        number = 1

    return f"{prefix}{number:03d}"


def get_customer_or_404(connection, customer_id):
    row = connection.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


def get_transaction_or_404(connection, transaction_id):
    row = connection.execute(
        "SELECT * FROM credit_transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Credit transaction not found")
    return row


def get_item_or_404(connection, item_id):
    row = connection.execute(
        "SELECT * FROM credited_items WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Credited item not found")
    return row


def get_payment_or_404(connection, payment_id):
    row = connection.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return row


def transaction_paid(connection, transaction_id):
    row = connection.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total_paid
        FROM payments
        WHERE transaction_id = ?
        """,
        (transaction_id,),
    ).fetchone()
    return float(row["total_paid"] or 0)


def calculate_transaction_status(connection, transaction):
    paid = transaction_paid(connection, transaction["id"])
    amount = float(transaction["amount"])
    remaining = max(amount - paid, 0)

    due = parse_date(transaction["due_date"])
    if remaining <= 0:
        return "Paid", paid, remaining
    if due is not None and date.today() > due:
        return "Overdue", paid, remaining
    return "Pending", paid, remaining


def refresh_transaction_status(connection, transaction_id):
    transaction = connection.execute(
        "SELECT * FROM credit_transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    if transaction is None:
        return None

    status, paid, remaining = calculate_transaction_status(connection, transaction)
    connection.execute(
        "UPDATE credit_transactions SET status = ? WHERE id = ?",
        (status, transaction_id),
    )
    return status, paid, remaining


def refresh_all_statuses(connection):
    rows = connection.execute("SELECT id FROM credit_transactions").fetchall()
    for row in rows:
        refresh_transaction_status(connection, row["id"])
    connection.commit()


# =========================================================
# ROOT / HEALTH
# =========================================================

@app.get("/")
def home():
    return {
        "success": True,
        "message": "Udhaar Management System Backend is running",
        "database": "SQLite",
        "version": "2.0.0",
    }


@app.get("/health")
def health():
    connection = get_connection()
    try:
        connection.execute("SELECT 1").fetchone()
        return {"success": True, "database": "connected"}
    finally:
        connection.close()


# =========================================================
# LOGIN
# =========================================================

class LoginRequest(BaseModel):
    username: str
    password: str
    role: str


@app.post("/login")
def login(data: LoginRequest):
    connection = get_connection()
    try:
        user = connection.execute(
            """
            SELECT id, username, role
            FROM users
            WHERE username = ? AND password = ? AND role = ?
            """,
            (data.username, data.password, data.role),
        ).fetchone()

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid username, password or role",
            )

        return {
            "success": True,
            "message": "Login successful",
            "user": row_to_dict(user),
        }
    finally:
        connection.close()


# =========================================================
# CUSTOMERS
# =========================================================

class CustomerCreate(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    alternate_phone: str = ""
    email: str = ""
    address: str = ""
    performance: str = "Average"


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    performance: Optional[str] = None


@app.get("/customers")
def get_customers():
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM customers ORDER BY rowid DESC"
        ).fetchall()
        return {"success": True, "customers": [dict(r) for r in rows]}
    finally:
        connection.close()


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str):
    connection = get_connection()
    try:
        customer = get_customer_or_404(connection, customer_id)
        return {"success": True, "customer": dict(customer)}
    finally:
        connection.close()


@app.post("/customers")
def add_customer(data: CustomerCreate):
    if not data.name.strip() or not data.phone.strip():
        raise HTTPException(status_code=400, detail="Name and phone are required")

    connection = get_connection()
    try:
        customer_id = next_id(connection, "customers", "id", "C")
        now = today_ddmmyyyy()
        connection.execute(
            """
            INSERT INTO customers
            (id, name, phone, alternate_phone, email, address,
             performance, created_date, updated_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                data.name.strip(),
                data.phone.strip(),
                data.alternate_phone.strip(),
                data.email.strip(),
                data.address.strip(),
                data.performance or "Average",
                now,
                now,
            ),
        )
        connection.commit()
        customer = connection.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        return {
            "success": True,
            "message": "Customer added successfully",
            "customer": dict(customer),
        }
    finally:
        connection.close()


@app.put("/customers/{customer_id}")
def update_customer(customer_id: str, data: CustomerUpdate):
    connection = get_connection()
    try:
        existing = get_customer_or_404(connection, customer_id)
        values = {
            "name": existing["name"],
            "phone": existing["phone"],
            "alternate_phone": existing["alternate_phone"] or "",
            "email": existing["email"] or "",
            "address": existing["address"] or "",
            "performance": existing["performance"] or "Average",
        }
        for key in values:
            incoming = getattr(data, key)
            if incoming is not None:
                values[key] = incoming

        connection.execute(
            """
            UPDATE customers
            SET name=?, phone=?, alternate_phone=?, email=?, address=?,
                performance=?, updated_date=?
            WHERE id=?
            """,
            (
                values["name"], values["phone"], values["alternate_phone"],
                values["email"], values["address"], values["performance"],
                today_ddmmyyyy(), customer_id,
            ),
        )
        connection.commit()
        customer = connection.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        return {
            "success": True,
            "message": "Customer updated successfully",
            "customer": dict(customer),
        }
    finally:
        connection.close()


@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: str):
    connection = get_connection()
    try:
        get_customer_or_404(connection, customer_id)
        connection.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        connection.commit()
        return {"success": True, "message": "Customer deleted successfully"}
    finally:
        connection.close()


# =========================================================
# CREDIT TRANSACTIONS
# =========================================================

class TransactionCreate(BaseModel):
    customer_id: str
    transaction_date: str
    due_date: str
    amount: float = Field(gt=0)
    notes: str = ""


class TransactionUpdate(BaseModel):
    transaction_date: Optional[str] = None
    due_date: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    notes: Optional[str] = None
    status: Optional[str] = None


@app.get("/transactions")
def get_transactions():
    connection = get_connection()
    try:
        refresh_all_statuses(connection)
        rows = connection.execute(
            """
            SELECT t.*, c.name AS customer_name
            FROM credit_transactions t
            JOIN customers c ON t.customer_id = c.id
            ORDER BY t.rowid DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            _, paid, remaining = calculate_transaction_status(connection, row)
            item["total_paid"] = paid
            item["remaining_amount"] = remaining
            result.append(item)
        return {"success": True, "transactions": result}
    finally:
        connection.close()


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):
    connection = get_connection()
    try:
        transaction = get_transaction_or_404(connection, transaction_id)
        refresh_transaction_status(connection, transaction_id)
        connection.commit()
        transaction = get_transaction_or_404(connection, transaction_id)
        status, paid, remaining = calculate_transaction_status(connection, transaction)
        result = dict(transaction)
        result.update({"total_paid": paid, "remaining_amount": remaining, "status": status})
        return {"success": True, "transaction": result}
    finally:
        connection.close()


@app.post("/transactions")
def add_transaction(data: TransactionCreate):
    normalize_date(data.transaction_date, "transaction_date")
    normalize_date(data.due_date, "due_date")

    connection = get_connection()
    try:
        get_customer_or_404(connection, data.customer_id)
        transaction_id = next_id(
            connection, "credit_transactions", "id", "TR"
        )
        connection.execute(
            """
            INSERT INTO credit_transactions
            (id, customer_id, transaction_date, due_date, amount, status, notes)
            VALUES (?, ?, ?, ?, ?, 'Pending', ?)
            """,
            (
                transaction_id,
                data.customer_id,
                data.transaction_date,
                data.due_date,
                data.amount,
                data.notes,
            ),
        )
        connection.commit()
        refresh_transaction_status(connection, transaction_id)
        connection.commit()
        return {
            "success": True,
            "message": "Credit transaction added successfully",
            "transaction_id": transaction_id,
        }
    finally:
        connection.close()


@app.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: str, data: TransactionUpdate):
    connection = get_connection()
    try:
        existing = get_transaction_or_404(connection, transaction_id)
        transaction_date = data.transaction_date or existing["transaction_date"]
        due_date = data.due_date or existing["due_date"]
        amount = data.amount if data.amount is not None else existing["amount"]
        notes = data.notes if data.notes is not None else existing["notes"]

        normalize_date(transaction_date, "transaction_date")
        normalize_date(due_date, "due_date")

        paid = transaction_paid(connection, transaction_id)
        if amount < paid:
            raise HTTPException(
                status_code=400,
                detail=f"Amount cannot be less than total paid amount ₹{paid:.2f}",
            )

        connection.execute(
            """
            UPDATE credit_transactions
            SET transaction_date=?, due_date=?, amount=?, notes=?
            WHERE id=?
            """,
            (transaction_date, due_date, amount, notes, transaction_id),
        )
        connection.commit()
        refresh_transaction_status(connection, transaction_id)
        connection.commit()
        return {
            "success": True,
            "message": "Credit transaction updated successfully",
            "transaction_id": transaction_id,
        }
    finally:
        connection.close()


@app.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str):
    connection = get_connection()
    try:
        get_transaction_or_404(connection, transaction_id)
        item_count = connection.execute(
            "SELECT COUNT(*) AS count FROM credited_items WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()["count"]
        payment_count = connection.execute(
            "SELECT COUNT(*) AS count FROM payments WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()["count"]

        if item_count or payment_count:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete transaction because credited items or payments exist",
            )

        connection.execute(
            "DELETE FROM credit_transactions WHERE id=?", (transaction_id,)
        )
        connection.commit()
        return {"success": True, "message": "Credit transaction deleted successfully"}
    finally:
        connection.close()


# =========================================================
# CREDITED ITEMS
# =========================================================

class ItemCreate(BaseModel):
    transaction_id: str
    item_name: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    credited_date: str


class ItemUpdate(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    credited_date: Optional[str] = None


def item_response(row):
    result = dict(row)
    result["subtotal"] = float(result["quantity"]) * float(result["unit_price"])
    return result


@app.get("/items")
def get_items():
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT i.*, t.customer_id, c.name AS customer_name
            FROM credited_items i
            JOIN credit_transactions t ON i.transaction_id=t.id
            JOIN customers c ON t.customer_id=c.id
            ORDER BY i.rowid DESC
            """
        ).fetchall()
        return {"success": True, "items": [item_response(r) for r in rows]}
    finally:
        connection.close()


@app.get("/items/{item_id}")
def get_item(item_id: str):
    connection = get_connection()
    try:
        row = get_item_or_404(connection, item_id)
        return {"success": True, "item": item_response(row)}
    finally:
        connection.close()


@app.get("/transactions/{transaction_id}/items")
def get_transaction_items(transaction_id: str):
    connection = get_connection()
    try:
        get_transaction_or_404(connection, transaction_id)
        rows = connection.execute(
            "SELECT * FROM credited_items WHERE transaction_id=? ORDER BY rowid DESC",
            (transaction_id,),
        ).fetchall()
        return {"success": True, "items": [item_response(r) for r in rows]}
    finally:
        connection.close()


@app.post("/items")
def add_item(data: ItemCreate):
    normalize_date(data.credited_date, "credited_date")
    connection = get_connection()
    try:
        get_transaction_or_404(connection, data.transaction_id)
        item_id = next_id(connection, "credited_items", "id", "I")
        subtotal = float(data.quantity) * float(data.unit_price)
        connection.execute(
            """
            INSERT INTO credited_items
            (id, transaction_id, item_name, quantity, unit_price, subtotal, credited_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                data.transaction_id,
                data.item_name.strip(),
                data.quantity,
                data.unit_price,
                subtotal,
                data.credited_date,
            ),
        )
        connection.commit()
        return {
            "success": True,
            "message": "Credited item added successfully",
            "item_id": item_id,
            "subtotal": subtotal,
        }
    finally:
        connection.close()


@app.put("/items/{item_id}")
def update_item(item_id: str, data: ItemUpdate):
    connection = get_connection()
    try:
        existing = get_item_or_404(connection, item_id)
        item_name = data.item_name if data.item_name is not None else existing["item_name"]
        quantity = data.quantity if data.quantity is not None else existing["quantity"]
        unit_price = data.unit_price if data.unit_price is not None else existing["unit_price"]
        credited_date = data.credited_date or existing["credited_date"]
        normalize_date(credited_date, "credited_date")
        subtotal = float(quantity) * float(unit_price)

        connection.execute(
            """
            UPDATE credited_items
            SET item_name=?, quantity=?, unit_price=?, subtotal=?, credited_date=?
            WHERE id=?
            """,
            (item_name.strip(), quantity, unit_price, subtotal, credited_date, item_id),
        )
        connection.commit()
        return {"success": True, "message": "Credited item updated successfully"}
    finally:
        connection.close()


@app.delete("/items/{item_id}")
def delete_item(item_id: str):
    connection = get_connection()
    try:
        get_item_or_404(connection, item_id)
        connection.execute("DELETE FROM credited_items WHERE id=?", (item_id,))
        connection.commit()
        return {"success": True, "message": "Credited item deleted successfully"}
    finally:
        connection.close()


# =========================================================
# PAYMENTS
# =========================================================

ALLOWED_PAYMENT_METHODS = ["Cash", "UPI", "Bank Transfer", "Cheque"]


class PaymentCreate(BaseModel):
    customer_id: str
    transaction_id: str
    amount: float = Field(gt=0)
    payment_date: str
    payment_method: str
    reference_id: str = ""


class PaymentUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    payment_date: Optional[str] = None
    payment_method: Optional[str] = None
    reference_id: Optional[str] = None


@app.get("/payments")
def get_payments():
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT p.*, c.name AS customer_name
            FROM payments p
            JOIN customers c ON p.customer_id=c.id
            ORDER BY p.rowid DESC
            """
        ).fetchall()
        return {"success": True, "payments": [dict(r) for r in rows]}
    finally:
        connection.close()


@app.get("/payments/{payment_id}")
def get_payment(payment_id: str):
    connection = get_connection()
    try:
        row = get_payment_or_404(connection, payment_id)
        return {"success": True, "payment": dict(row)}
    finally:
        connection.close()


@app.get("/transactions/{transaction_id}/payments")
def get_transaction_payments(transaction_id: str):
    connection = get_connection()
    try:
        get_transaction_or_404(connection, transaction_id)
        rows = connection.execute(
            "SELECT * FROM payments WHERE transaction_id=? ORDER BY rowid DESC",
            (transaction_id,),
        ).fetchall()
        return {"success": True, "payments": [dict(r) for r in rows]}
    finally:
        connection.close()


@app.get("/transactions/{transaction_id}/payment-summary")
def payment_summary(transaction_id: str):
    connection = get_connection()
    try:
        transaction = get_transaction_or_404(connection, transaction_id)
        paid = transaction_paid(connection, transaction_id)
        amount = float(transaction["amount"])
        remaining = max(amount - paid, 0)
        status, _, _ = calculate_transaction_status(connection, transaction)
        return {
            "success": True,
            "transaction_id": transaction_id,
            "transaction_amount": amount,
            "total_paid": paid,
            "remaining_amount": remaining,
            "status": status,
        }
    finally:
        connection.close()


@app.post("/payments")
def add_payment(data: PaymentCreate):
    normalize_date(data.payment_date, "payment_date")
    if data.payment_method not in ALLOWED_PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Invalid payment method")

    connection = get_connection()
    try:
        get_customer_or_404(connection, data.customer_id)
        transaction = get_transaction_or_404(connection, data.transaction_id)

        if transaction["customer_id"] != data.customer_id:
            raise HTTPException(
                status_code=400,
                detail="Transaction does not belong to this customer",
            )

        paid = transaction_paid(connection, data.transaction_id)
        remaining = max(float(transaction["amount"]) - paid, 0)
        if data.amount > remaining:
            raise HTTPException(
                status_code=400,
                detail=f"Payment exceeds remaining amount. Remaining amount is ₹{remaining:.2f}",
            )

        payment_id = next_id(connection, "payments", "id", "P")
        connection.execute(
            """
            INSERT INTO payments
            (id, customer_id, transaction_id, amount, payment_date, payment_method, reference_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                data.customer_id,
                data.transaction_id,
                data.amount,
                data.payment_date,
                data.payment_method,
                data.reference_id,
            ),
        )
        connection.commit()
        refresh_transaction_status(connection, data.transaction_id)
        connection.commit()

        return {
            "success": True,
            "message": "Payment added successfully",
            "payment_id": payment_id,
            "remaining_amount": max(remaining - data.amount, 0),
        }
    finally:
        connection.close()


@app.put("/payments/{payment_id}")
def update_payment(payment_id: str, data: PaymentUpdate):
    connection = get_connection()
    try:
        existing = get_payment_or_404(connection, payment_id)
        amount = data.amount if data.amount is not None else existing["amount"]
        payment_date = data.payment_date or existing["payment_date"]
        payment_method = data.payment_method or existing["payment_method"]
        reference_id = data.reference_id if data.reference_id is not None else existing["reference_id"]

        normalize_date(payment_date, "payment_date")
        if payment_method not in ALLOWED_PAYMENT_METHODS:
            raise HTTPException(status_code=400, detail="Invalid payment method")

        transaction = get_transaction_or_404(connection, existing["transaction_id"])
        other_paid = connection.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total_paid
            FROM payments
            WHERE transaction_id=? AND id != ?
            """,
            (existing["transaction_id"], payment_id),
        ).fetchone()["total_paid"]
        remaining_for_this = max(float(transaction["amount"]) - float(other_paid), 0)
        if amount > remaining_for_this:
            raise HTTPException(
                status_code=400,
                detail=f"Payment exceeds remaining amount. Maximum allowed is ₹{remaining_for_this:.2f}",
            )

        connection.execute(
            """
            UPDATE payments
            SET amount=?, payment_date=?, payment_method=?, reference_id=?
            WHERE id=?
            """,
            (amount, payment_date, payment_method, reference_id, payment_id),
        )
        connection.commit()
        refresh_transaction_status(connection, existing["transaction_id"])
        connection.commit()
        return {"success": True, "message": "Payment updated successfully"}
    finally:
        connection.close()


@app.delete("/payments/{payment_id}")
def delete_payment(payment_id: str):
    connection = get_connection()
    try:
        payment = get_payment_or_404(connection, payment_id)
        connection.execute("DELETE FROM payments WHERE id=?", (payment_id,))
        connection.commit()
        refresh_transaction_status(connection, payment["transaction_id"])
        connection.commit()
        return {"success": True, "message": "Payment deleted successfully"}
    finally:
        connection.close()


# =========================================================
# OUTSTANDING BALANCE
# =========================================================

@app.get("/outstanding")
def get_outstanding_balances():
    connection = get_connection()
    try:
        refresh_all_statuses(connection)
        customers = connection.execute(
            "SELECT id, name FROM customers ORDER BY id"
        ).fetchall()
        result = []

        for customer in customers:
            due = connection.execute(
                "SELECT COALESCE(SUM(amount),0) AS total_due FROM credit_transactions WHERE customer_id=?",
                (customer["id"],),
            ).fetchone()["total_due"]
            paid = connection.execute(
                "SELECT COALESCE(SUM(amount),0) AS total_paid FROM payments WHERE customer_id=?",
                (customer["id"],),
            ).fetchone()["total_paid"]
            pending = max(float(due) - float(paid), 0)

            unpaid = connection.execute(
                """
                SELECT id, due_date, amount, status
                FROM credit_transactions
                WHERE customer_id=? AND status != 'Paid'
                ORDER BY due_date ASC
                LIMIT 1
                """,
                (customer["id"],),
            ).fetchone()

            result.append({
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "total_due": float(due),
                "total_paid": float(paid),
                "pending_amount": pending,
                "due_date": unpaid["due_date"] if unpaid else None,
                "status": unpaid["status"] if unpaid else "Paid",
            })

        return {"success": True, "outstanding": result}
    finally:
        connection.close()


@app.get("/outstanding/{customer_id}")
def get_customer_outstanding(customer_id: str):
    connection = get_connection()
    try:
        customer = get_customer_or_404(connection, customer_id)
        transactions = connection.execute(
            "SELECT * FROM credit_transactions WHERE customer_id=? ORDER BY due_date ASC",
            (customer_id,),
        ).fetchall()

        total_due = 0.0
        total_paid = 0.0
        details = []

        for transaction in transactions:
            status, paid, remaining = calculate_transaction_status(connection, transaction)
            total_due += float(transaction["amount"])
            total_paid += paid
            details.append({
                "transaction_id": transaction["id"],
                "transaction_date": transaction["transaction_date"],
                "due_date": transaction["due_date"],
                "amount": float(transaction["amount"]),
                "total_paid": paid,
                "remaining_amount": remaining,
                "status": status,
                "notes": transaction["notes"],
            })

        pending = max(total_due - total_paid, 0)
        if pending == 0:
            overall = "Paid"
        elif any(t["status"] == "Overdue" for t in details):
            overall = "Overdue"
        else:
            overall = "Pending"

        return {
            "success": True,
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "total_due": total_due,
            "total_paid": total_paid,
            "pending_amount": pending,
            "status": overall,
            "transactions": details,
        }
    finally:
        connection.close()


# =========================================================
# CUSTOMER PERFORMANCE
# =========================================================

@app.get("/customer-performance")
def customer_performance():
    connection = get_connection()
    try:
        refresh_all_statuses(connection)
        customers = connection.execute(
            "SELECT id, name FROM customers ORDER BY id"
        ).fetchall()
        result = []

        for customer in customers:
            transactions = connection.execute(
                "SELECT * FROM credit_transactions WHERE customer_id=?",
                (customer["id"],),
            ).fetchall()
            total_credit = sum(float(t["amount"]) for t in transactions)
            total_paid = sum(transaction_paid(connection, t["id"]) for t in transactions)
            pending = max(total_credit - total_paid, 0)
            overdue_count = sum(
                1 for t in transactions
                if calculate_transaction_status(connection, t)[0] == "Overdue"
            )
            paid_on_time = sum(
                1 for t in transactions
                if calculate_transaction_status(connection, t)[0] == "Paid"
                and (parse_date(t["due_date"]) is None or
                     (parse_date(t["due_date"]) >= parse_date(t["transaction_date"])))
            )

            if not transactions or total_credit == 0:
                performance = "Average"
            elif overdue_count > 0:
                performance = "Poor"
            elif pending == 0:
                performance = "Excellent"
            elif total_paid / total_credit >= 0.75:
                performance = "Good"
            else:
                performance = "Average"

            payment_percentage = (total_paid / total_credit * 100) if total_credit else 0
            result.append({
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "total_credit": total_credit,
                "total_paid": total_paid,
                "pending_amount": pending,
                "payment_percentage": round(payment_percentage, 2),
                "overdue_transactions": overdue_count,
                "paid_transactions": paid_on_time,
                "performance": performance,
            })

        return {"success": True, "performance": result}
    finally:
        connection.close()


@app.get("/customer-performance/{customer_id}")
def one_customer_performance(customer_id: str):
    all_data = customer_performance()["performance"]
    for item in all_data:
        if item["customer_id"] == customer_id:
            return {"success": True, "performance": item}
    raise HTTPException(status_code=404, detail="Customer not found")


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/dashboard")
def get_dashboard():
    connection = get_connection()
    try:
        refresh_all_statuses(connection)
        total_customers = connection.execute(
            "SELECT COUNT(*) AS count FROM customers"
        ).fetchone()["count"]
        total_transactions = connection.execute(
            "SELECT COUNT(*) AS count FROM credit_transactions"
        ).fetchone()["count"]
        total_credit = connection.execute(
            "SELECT COALESCE(SUM(amount),0) AS value FROM credit_transactions"
        ).fetchone()["value"]
        total_payments = connection.execute(
            "SELECT COALESCE(SUM(amount),0) AS value FROM payments"
        ).fetchone()["value"]
        total_items = connection.execute(
            "SELECT COUNT(*) AS count FROM credited_items"
        ).fetchone()["count"]
        total_payment_records = connection.execute(
            "SELECT COUNT(*) AS count FROM payments"
        ).fetchone()["count"]
        pending = connection.execute(
            "SELECT COUNT(*) AS count FROM credit_transactions WHERE status='Pending'"
        ).fetchone()["count"]
        overdue = connection.execute(
            "SELECT COUNT(*) AS count FROM credit_transactions WHERE status='Overdue'"
        ).fetchone()["count"]
        paid = connection.execute(
            "SELECT COUNT(*) AS count FROM credit_transactions WHERE status='Paid'"
        ).fetchone()["count"]

        outstanding = max(float(total_credit) - float(total_payments), 0)

        return {
            "success": True,
            "total_customers": total_customers,
            "total_transactions": total_transactions,
            "total_credit": float(total_credit),
            "total_payments": float(total_payments),
            "total_outstanding": outstanding,
            "pending_transactions": pending,
            "overdue_transactions": overdue,
            "paid_transactions": paid,
            "total_items": total_items,
            "total_payment_records": total_payment_records,
        }
    finally:
        connection.close()


# =========================================================
# REPORTS
# =========================================================

@app.get("/reports/summary")
def report_summary():
    dashboard = get_dashboard()
    return {"success": True, "report": dashboard}


@app.get("/reports/transactions")
def report_transactions():
    return get_transactions()


@app.get("/reports/payments")
def report_payments():
    return get_payments()


@app.get("/reports/outstanding")
def report_outstanding():
    return get_outstanding_balances()


@app.get("/reports/customers")
def report_customers():
    return get_customers()
