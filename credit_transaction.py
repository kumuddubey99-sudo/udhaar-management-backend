# ============================================================
# CREDIT TRANSACTION MODELS
# ============================================================

class TransactionCreate(BaseModel):
    customer_id: str
    transaction_date: str
    due_date: str
    amount: float
    notes: Optional[str] = ""


class TransactionUpdate(BaseModel):
    transaction_date: Optional[str] = None
    due_date: Optional[str] = None
    amount: Optional[float] = None
    payment_status: Optional[str] = None
    notes: Optional[str] = None

# ============================================================
# GET ALL CREDIT TRANSACTIONS
# ============================================================

@app.get("/transactions")
def get_transactions():
    conn = get_connection()

    transactions = conn.execute("""
        SELECT
            t.transaction_id,
            t.customer_id,
            c.customer_name,
            t.transaction_date,
            t.due_date,
            t.amount,
            t.payment_status,
            t.notes
        FROM credit_transactions t
        JOIN customers c
            ON t.customer_id = c.customer_id
        ORDER BY t.transaction_date DESC
    """).fetchall()

    conn.close()

    return [dict(row) for row in transactions]
# ============================================================
# ADD CREDIT TRANSACTION
# ============================================================

@app.post("/transactions")
def add_transaction(transaction: TransactionCreate):

    conn = get_connection()

    # Check whether customer exists
    customer = conn.execute(
        "SELECT customer_id FROM customers WHERE customer_id = ?",
        (transaction.customer_id,)
    ).fetchone()

    if not customer:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    # Check amount
    if transaction.amount <= 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Amount must be greater than 0"
        )

    # Generate transaction ID
    last_transaction = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
        ORDER BY rowid DESC
        LIMIT 1
    """).fetchone()

    if last_transaction:
        last_id = last_transaction["transaction_id"]

        try:
            number = int(last_id.replace("TR", ""))
            new_number = number + 1
        except ValueError:
            new_number = 1
    else:
        new_number = 1

    transaction_id = f"TR{new_number:03d}"

    # Initially transaction is Pending
    payment_status = "Pending"

    conn.execute("""
        INSERT INTO credit_transactions (
            transaction_id,
            customer_id,
            transaction_date,
            due_date,
            amount,
            payment_status,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        transaction_id,
        transaction.customer_id,
        transaction.transaction_date,
        transaction.due_date,
        transaction.amount,
        payment_status,
        transaction.notes
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Credit transaction added successfully",
        "transaction_id": transaction_id
    }
# ============================================================
# GET ONE CREDIT TRANSACTION
# ============================================================

@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):

    conn = get_connection()

    transaction = conn.execute("""
        SELECT
            t.transaction_id,
            t.customer_id,
            c.customer_name,
            t.transaction_date,
            t.due_date,
            t.amount,
            t.payment_status,
            t.notes
        FROM credit_transactions t
        JOIN customers c
            ON t.customer_id = c.customer_id
        WHERE t.transaction_id = ?
    """, (transaction_id,)).fetchone()

    conn.close()

    if not transaction:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    return dict(transaction)
# ============================================================
# UPDATE CREDIT TRANSACTION
# ============================================================

@app.put("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: str,
    transaction: TransactionUpdate
):

    conn = get_connection()

    existing = conn.execute("""
        SELECT *
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if not existing:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    # Use old values if new values are not provided
    transaction_date = (
        transaction.transaction_date
        if transaction.transaction_date is not None
        else existing["transaction_date"]
    )

    due_date = (
        transaction.due_date
        if transaction.due_date is not None
        else existing["due_date"]
    )

    amount = (
        transaction.amount
        if transaction.amount is not None
        else existing["amount"]
    )

    payment_status = (
        transaction.payment_status
        if transaction.payment_status is not None
        else existing["payment_status"]
    )

    notes = (
        transaction.notes
        if transaction.notes is not None
        else existing["notes"]
    )

    if amount <= 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Amount must be greater than 0"
        )

    # Check valid payment status
    allowed_status = [
        "Pending",
        "Paid",
        "Overdue"
    ]

    if payment_status not in allowed_status:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Invalid payment status"
        )

    conn.execute("""
        UPDATE credit_transactions
        SET
            transaction_date = ?,
            due_date = ?,
            amount = ?,
            payment_status = ?,
            notes = ?
        WHERE transaction_id = ?
    """, (
        transaction_date,
        due_date,
        amount,
        payment_status,
        notes,
        transaction_id
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Credit transaction updated successfully",
        "transaction_id": transaction_id
    }
# ============================================================
# DELETE CREDIT TRANSACTION
# ============================================================

@app.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str):

    conn = get_connection()

    existing = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if not existing:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    # Check credited items
    items = conn.execute("""
        SELECT COUNT(*) AS count
        FROM credited_items
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if items["count"] > 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete transaction because credited items exist"
        )

    # Check payments
    payments = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if payments["count"] > 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete transaction because payments exist"
        )

    conn.execute("""
        DELETE FROM credit_transactions
        WHERE transaction_id = ?
    """, (transaction_id,))

    conn.commit()
    conn.close()

    return {
        "message": "Credit transaction deleted successfully",
        "transaction_id": transaction_id
    }
