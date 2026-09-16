# ============================================================
# PAYMENT MODELS
# ============================================================

class PaymentCreate(BaseModel):
    customer_id: str
    transaction_id: str
    payment_amount: float
    payment_date: str
    payment_method: str
    reference_id: Optional[str] = ""


class PaymentUpdate(BaseModel):
    payment_amount: Optional[float] = None
    payment_date: Optional[str] = None
    payment_method: Optional[str] = None
    reference_id: Optional[str] = None
# ============================================================
# PAYMENT METHODS
# ============================================================

ALLOWED_PAYMENT_METHODS = [
    "Cash",
    "UPI",
    "Bank Transfer",
    "Cheque"
]
# ============================================================
# CALCULATE TRANSACTION STATUS
# ============================================================

def update_transaction_status(conn, transaction_id):

    transaction = conn.execute("""
        SELECT
            amount,
            due_date
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if not transaction:
        return

    # Calculate total payment made
    payment_result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
        FROM payments
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    total_paid = payment_result["total_paid"]
    transaction_amount = transaction["amount"]

    # Calculate remaining amount
    remaining_amount = transaction_amount - total_paid

    # Avoid negative balance
    if remaining_amount < 0:
        remaining_amount = 0

    # Determine status
    from datetime import datetime

    today = datetime.now().date()

    try:
        due_date = datetime.strptime(
            transaction["due_date"],
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        due_date = None

    if remaining_amount == 0:
        status = "Paid"

    elif due_date and today > due_date:
        status = "Overdue"

    else:
        status = "Pending"

    # Update transaction status
    conn.execute("""
        UPDATE credit_transactions
        SET payment_status = ?
        WHERE transaction_id = ?
    """, (
        status,
        transaction_id
    ))

    conn.commit()
# ============================================================
# GET ALL PAYMENTS
# ============================================================

@app.get("/payments")
def get_payments():

    conn = get_connection()

    payments = conn.execute("""
        SELECT
            p.payment_id,
            p.customer_id,
            c.customer_name,
            p.transaction_id,
            p.payment_amount,
            p.payment_date,
            p.payment_method,
            p.reference_id
        FROM payments p
        JOIN customers c
            ON p.customer_id = c.customer_id
        ORDER BY p.payment_date DESC
    """).fetchall()

    conn.close()

    return [dict(row) for row in payments]
# ============================================================
# ADD PAYMENT
# ============================================================

@app.post("/payments")
def add_payment(payment: PaymentCreate):

    conn = get_connection()

    # --------------------------------------------------------
    # Check customer
    # --------------------------------------------------------

    customer = conn.execute("""
        SELECT customer_id
        FROM customers
        WHERE customer_id = ?
    """, (
        payment.customer_id,
    )).fetchone()

    if not customer:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    # --------------------------------------------------------
    # Check transaction
    # --------------------------------------------------------

    transaction = conn.execute("""
        SELECT
            transaction_id,
            customer_id,
            amount
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        payment.transaction_id,
    )).fetchone()

    if not transaction:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    # --------------------------------------------------------
    # Make sure transaction belongs to customer
    # --------------------------------------------------------

    if transaction["customer_id"] != payment.customer_id:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Transaction does not belong to this customer"
        )

    # --------------------------------------------------------
    # Validate payment amount
    # --------------------------------------------------------

    if payment.payment_amount <= 0:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than 0"
        )

    # --------------------------------------------------------
    # Validate payment method
    # --------------------------------------------------------

    if payment.payment_method not in ALLOWED_PAYMENT_METHODS:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Invalid payment method"
        )

    # --------------------------------------------------------
    # Calculate already paid amount
    # --------------------------------------------------------

    result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
        FROM payments
        WHERE transaction_id = ?
    """, (
        payment.transaction_id,
    )).fetchone()

    total_paid = result["total_paid"]

    # --------------------------------------------------------
    # Calculate remaining amount
    # --------------------------------------------------------

    transaction_amount = transaction["amount"]

    remaining_amount = transaction_amount - total_paid

    # --------------------------------------------------------
    # Prevent overpayment
    # --------------------------------------------------------

    if payment.payment_amount > remaining_amount:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail=(
                f"Payment exceeds remaining amount. "
                f"Remaining amount is ₹{remaining_amount:.2f}"
            )
        )

    # --------------------------------------------------------
    # Generate Payment ID
    # --------------------------------------------------------

    last_payment = conn.execute("""
        SELECT payment_id
        FROM payments
        ORDER BY rowid DESC
        LIMIT 1
    """).fetchone()

    if last_payment:

        last_id = last_payment["payment_id"]

        try:
            number = int(last_id.replace("P", ""))
            new_number = number + 1

        except ValueError:
            new_number = 1

    else:
        new_number = 1

    payment_id = f"P{new_number:03d}"

    # --------------------------------------------------------
    # Insert payment
    # --------------------------------------------------------

    conn.execute("""
        INSERT INTO payments (
            payment_id,
            customer_id,
            transaction_id,
            payment_amount,
            payment_date,
            payment_method,
            reference_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        payment_id,
        payment.customer_id,
        payment.transaction_id,
        payment.payment_amount,
        payment.payment_date,
        payment.payment_method,
        payment.reference_id
    ))

    conn.commit()

    # --------------------------------------------------------
    # Update transaction status
    # --------------------------------------------------------

    update_transaction_status(
        conn,
        payment.transaction_id
    )

    # --------------------------------------------------------
    # Calculate new remaining amount
    # --------------------------------------------------------

    new_total_paid = total_paid + payment.payment_amount

    new_remaining = transaction_amount - new_total_paid

    if new_remaining < 0:
        new_remaining = 0

    # Get updated status
    updated_transaction = conn.execute("""
        SELECT payment_status
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        payment.transaction_id,
    )).fetchone()

    status = updated_transaction["payment_status"]

    conn.close()

    return {
        "message": "Payment added successfully",
        "payment_id": payment_id,
        "transaction_id": payment.transaction_id,
        "transaction_amount": transaction_amount,
        "total_paid": new_total_paid,
        "remaining_amount": new_remaining,
        "status": status
    }
# ============================================================
# GET ONE PAYMENT
# ============================================================

@app.get("/payments/{payment_id}")
def get_payment(payment_id: str):

    conn = get_connection()

    payment = conn.execute("""
        SELECT
            p.payment_id,
            p.customer_id,
            c.customer_name,
            p.transaction_id,
            p.payment_amount,
            p.payment_date,
            p.payment_method,
            p.reference_id
        FROM payments p
        JOIN customers c
            ON p.customer_id = c.customer_id
        WHERE p.payment_id = ?
    """, (
        payment_id,
    )).fetchone()

    conn.close()

    if not payment:

        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    return dict(payment)
# ============================================================
# GET PAYMENTS FOR A TRANSACTION
# ============================================================

@app.get("/transactions/{transaction_id}/payments")
def get_transaction_payments(transaction_id: str):

    conn = get_connection()

    transaction = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    if not transaction:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    payments = conn.execute("""
        SELECT
            payment_id,
            customer_id,
            transaction_id,
            payment_amount,
            payment_date,
            payment_method,
            reference_id
        FROM payments
        WHERE transaction_id = ?
        ORDER BY payment_date DESC
    """, (
        transaction_id,
    )).fetchall()

    conn.close()

    return [dict(row) for row in payments]
# ============================================================
# TRANSACTION PAYMENT SUMMARY
# ============================================================

@app.get("/transactions/{transaction_id}/payment-summary")
def payment_summary(transaction_id: str):

    conn = get_connection()

    transaction = conn.execute("""
        SELECT
            transaction_id,
            customer_id,
            amount,
            due_date
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    if not transaction:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
        FROM payments
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    total_paid = result["total_paid"]

    total_amount = transaction["amount"]

    remaining_amount = total_amount - total_paid

    if remaining_amount < 0:
        remaining_amount = 0

    # Make sure status is current
    update_transaction_status(
        conn,
        transaction_id
    )

    updated = conn.execute("""
        SELECT payment_status
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    status = updated["payment_status"]

    conn.close()

    return {
        "transaction_id": transaction_id,
        "customer_id": transaction["customer_id"],
        "total_amount": total_amount,
        "total_paid": total_paid,
        "remaining_amount": remaining_amount,
        "due_date": transaction["due_date"],
        "status": status
    }
# ============================================================
# UPDATE PAYMENT
# ============================================================

@app.put("/payments/{payment_id}")
def update_payment(
    payment_id: str,
    payment: PaymentUpdate
):

    conn = get_connection()

    existing = conn.execute("""
        SELECT *
        FROM payments
        WHERE payment_id = ?
    """, (
        payment_id,
    )).fetchone()

    if not existing:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    payment_amount = (
        payment.payment_amount
        if payment.payment_amount is not None
        else existing["payment_amount"]
    )

    payment_date = (
        payment.payment_date
        if payment.payment_date is not None
        else existing["payment_date"]
    )

    payment_method = (
        payment.payment_method
        if payment.payment_method is not None
        else existing["payment_method"]
    )

    reference_id = (
        payment.reference_id
        if payment.reference_id is not None
        else existing["reference_id"]
    )

    # Validate amount

    if payment_amount <= 0:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than 0"
        )

    # Validate payment method

    if payment_method not in ALLOWED_PAYMENT_METHODS:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Invalid payment method"
        )

    transaction_id = existing["transaction_id"]

    # Get transaction amount

    transaction = conn.execute("""
        SELECT amount
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    transaction_amount = transaction["amount"]

    # Calculate other payments
    result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
        FROM payments
        WHERE transaction_id = ?
        AND payment_id != ?
    """, (
        transaction_id,
        payment_id
    )).fetchone()

    other_payments = result["total_paid"]

    # Check new payment does not exceed balance

    if other_payments + payment_amount > transaction_amount:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Updated payment exceeds transaction amount"
        )

    # Update payment

    conn.execute("""
        UPDATE payments
        SET
            payment_amount = ?,
            payment_date = ?,
            payment_method = ?,
            reference_id = ?
        WHERE payment_id = ?
    """, (
        payment_amount,
        payment_date,
        payment_method,
        reference_id,
        payment_id
    ))

    conn.commit()

    # Recalculate status

    update_transaction_status(
        conn,
        transaction_id
    )

    # Calculate new totals

    new_total_paid = other_payments + payment_amount

    remaining_amount = transaction_amount - new_total_paid

    if remaining_amount < 0:
        remaining_amount = 0

    updated = conn.execute("""
        SELECT payment_status
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    status = updated["payment_status"]

    conn.close()

    return {
        "message": "Payment updated successfully",
        "payment_id": payment_id,
        "total_paid": new_total_paid,
        "remaining_amount": remaining_amount,
        "status": status
    }
# ============================================================
# DELETE PAYMENT
# ============================================================

@app.delete("/payments/{payment_id}")
def delete_payment(payment_id: str):

    conn = get_connection()

    existing = conn.execute("""
        SELECT *
        FROM payments
        WHERE payment_id = ?
    """, (
        payment_id,
    )).fetchone()

    if not existing:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    transaction_id = existing["transaction_id"]

    # Delete payment

    conn.execute("""
        DELETE FROM payments
        WHERE payment_id = ?
    """, (
        payment_id,
    ))

    conn.commit()

    # Recalculate transaction status

    update_transaction_status(
        conn,
        transaction_id
    )

    # Get new summary

    transaction = conn.execute("""
        SELECT amount, payment_status
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
        FROM payments
        WHERE transaction_id = ?
    """, (
        transaction_id,
    )).fetchone()

    total_paid = result["total_paid"]

    remaining_amount = transaction["amount"] - total_paid

    if remaining_amount < 0:
        remaining_amount = 0

    status = transaction["payment_status"]

    conn.close()

    return {
        "message": "Payment deleted successfully",
        "payment_id": payment_id,
        "total_paid": total_paid,
        "remaining_amount": remaining_amount,
        "status": status
    }

