# ============================================================
# OUTSTANDING BALANCE
# ============================================================

@app.get("/outstanding")
def get_outstanding_balances():

    conn = get_connection()

    customers = conn.execute("""
        SELECT
            customer_id,
            customer_name
        FROM customers
        ORDER BY customer_id
    """).fetchall()

    result = []

    from datetime import datetime

    for customer in customers:

        customer_id = customer["customer_id"]

        # ----------------------------------------------------
        # Total credit amount
        # ----------------------------------------------------

        due_result = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_due
            FROM credit_transactions
            WHERE customer_id = ?
        """, (
            customer_id,
        )).fetchone()

        total_due = due_result["total_due"]

        # ----------------------------------------------------
        # Total payments
        # ----------------------------------------------------

        paid_result = conn.execute("""
            SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
            FROM payments
            WHERE customer_id = ?
        """, (
            customer_id,
        )).fetchone()

        total_paid = paid_result["total_paid"]

        # ----------------------------------------------------
        # Pending amount
        # ----------------------------------------------------

        pending_amount = total_due - total_paid

        if pending_amount < 0:
            pending_amount = 0

        # ----------------------------------------------------
        # Get latest unpaid transaction
        # ----------------------------------------------------

        transaction = conn.execute("""
            SELECT
                transaction_id,
                due_date,
                amount
            FROM credit_transactions
            WHERE customer_id = ?
            AND payment_status != 'Paid'
            ORDER BY due_date ASC
            LIMIT 1
        """, (
            customer_id,
        )).fetchone()

        due_date = None
        status = "Paid"

        if transaction:

            due_date = transaction["due_date"]

            try:
                due = datetime.strptime(
                    due_date,
                    "%Y-%m-%d"
                ).date()

                today = datetime.now().date()

                if today > due:
                    status = "Overdue"
                else:
                    status = "Pending"

            except (ValueError, TypeError):

                status = "Pending"

        # ----------------------------------------------------
        # Update all customer transaction statuses
        # ----------------------------------------------------

        transaction_rows = conn.execute("""
            SELECT transaction_id
            FROM credit_transactions
            WHERE customer_id = ?
        """, (
            customer_id,
        )).fetchall()

        for transaction_row in transaction_rows:

            update_transaction_status(
                conn,
                transaction_row["transaction_id"]
            )

        result.append({
            "customer_id": customer_id,
            "customer_name": customer["customer_name"],
            "total_due": total_due,
            "total_paid": total_paid,
            "pending_amount": pending_amount,
            "due_date": due_date,
            "status": status
        })

    conn.close()

    return result
# ============================================================
# OUTSTANDING BALANCE FOR ONE CUSTOMER
# ============================================================

@app.get("/outstanding/{customer_id}")
def get_customer_outstanding(customer_id: str):

    conn = get_connection()

    # --------------------------------------------------------
    # Check customer
    # --------------------------------------------------------

    customer = conn.execute("""
        SELECT
            customer_id,
            customer_name
        FROM customers
        WHERE customer_id = ?
    """, (
        customer_id,
    )).fetchone()

    if not customer:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    # --------------------------------------------------------
    # Update transaction statuses
    # --------------------------------------------------------

    transactions = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
        WHERE customer_id = ?
    """, (
        customer_id,
    )).fetchall()

    for transaction in transactions:

        update_transaction_status(
            conn,
            transaction["transaction_id"]
        )

    # --------------------------------------------------------
    # Total due
    # --------------------------------------------------------

    due_result = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total_due
        FROM credit_transactions
        WHERE customer_id = ?
    """, (
        customer_id,
    )).fetchone()

    total_due = due_result["total_due"]

    # --------------------------------------------------------
    # Total paid
    # --------------------------------------------------------

    paid_result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
        FROM payments
        WHERE customer_id = ?
    """, (
        customer_id,
    )).fetchone()

    total_paid = paid_result["total_paid"]

    # --------------------------------------------------------
    # Remaining amount
    # --------------------------------------------------------

    pending_amount = total_due - total_paid

    if pending_amount < 0:
        pending_amount = 0

    # --------------------------------------------------------
    # Get unpaid transactions
    # --------------------------------------------------------

    unpaid_transactions = conn.execute("""
        SELECT
            transaction_id,
            transaction_date,
            due_date,
            amount,
            payment_status,
            notes
        FROM credit_transactions
        WHERE customer_id = ?
        AND payment_status != 'Paid'
        ORDER BY due_date ASC
    """, (
        customer_id,
    )).fetchall()

    # --------------------------------------------------------
    # Prepare transaction details
    # --------------------------------------------------------

    transaction_details = []

    from datetime import datetime

    for transaction in unpaid_transactions:

        # Get payments for this transaction

        paid = conn.execute("""
            SELECT COALESCE(SUM(payment_amount), 0) AS total_paid
            FROM payments
            WHERE transaction_id = ?
        """, (
            transaction["transaction_id"],
        )).fetchone()

        transaction_paid = paid["total_paid"]

        transaction_remaining = (
            transaction["amount"] - transaction_paid
        )

        if transaction_remaining < 0:
            transaction_remaining = 0

        # Determine current status

        try:

            due = datetime.strptime(
                transaction["due_date"],
                "%Y-%m-%d"
            ).date()

            today = datetime.now().date()

            if transaction_remaining == 0:
                transaction_status = "Paid"

            elif today > due:
                transaction_status = "Overdue"

            else:
                transaction_status = "Pending"

        except (ValueError, TypeError):

            transaction_status = "Pending"

        transaction_details.append({
            "transaction_id": transaction["transaction_id"],
            "transaction_date": transaction["transaction_date"],
            "due_date": transaction["due_date"],
            "amount": transaction["amount"],
            "total_paid": transaction_paid,
            "remaining_amount": transaction_remaining,
            "status": transaction_status,
            "notes": transaction["notes"]
        })

    # --------------------------------------------------------
    # Overall customer status
    # --------------------------------------------------------

    if pending_amount == 0:

        overall_status = "Paid"

    else:

        overdue_found = any(
            item["status"] == "Overdue"
            for item in transaction_details
        )

        if overdue_found:
            overall_status = "Overdue"
        else:
            overall_status = "Pending"

    conn.close()

    return {
        "customer_id": customer["customer_id"],
        "customer_name": customer["customer_name"],
        "total_due": total_due,
        "total_paid": total_paid,
        "pending_amount": pending_amount,
        "status": overall_status,
        "transactions": transaction_details
    }
# First update statuses
for transaction in transaction_rows:
    update_transaction_status(
        conn,
        transaction["transaction_id"]
    )

# Then query unpaid transactions