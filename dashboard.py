# ============================================================
# DASHBOARD
# ============================================================

@app.get("/dashboard")
def get_dashboard():

    conn = get_connection()

    # --------------------------------------------------------
    # Update all transaction statuses first
    # --------------------------------------------------------

    transactions = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
    """).fetchall()

    for transaction in transactions:

        update_transaction_status(
            conn,
            transaction["transaction_id"]
        )

    # --------------------------------------------------------
    # Total Customers
    # --------------------------------------------------------

    customer_result = conn.execute("""
        SELECT COUNT(*) AS total_customers
        FROM customers
    """).fetchone()

    total_customers = customer_result["total_customers"]

    # --------------------------------------------------------
    # Total Credit
    # --------------------------------------------------------

    credit_result = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total_credit
        FROM credit_transactions
    """).fetchone()

    total_credit = credit_result["total_credit"]

    # --------------------------------------------------------
    # Total Payments
    # --------------------------------------------------------

    payment_result = conn.execute("""
        SELECT COALESCE(SUM(payment_amount), 0) AS total_payments
        FROM payments
    """).fetchone()

    total_payments = payment_result["total_payments"]

    # --------------------------------------------------------
    # Total Outstanding
    # --------------------------------------------------------

    total_outstanding = total_credit - total_payments

    if total_outstanding < 0:
        total_outstanding = 0

    # --------------------------------------------------------
    # Pending Transactions
    # --------------------------------------------------------

    pending_result = conn.execute("""
        SELECT COUNT(*) AS count
        FROM credit_transactions
        WHERE payment_status = 'Pending'
    """).fetchone()

    pending_transactions = pending_result["count"]

    # --------------------------------------------------------
    # Overdue Transactions
    # --------------------------------------------------------

    overdue_result = conn.execute("""
        SELECT COUNT(*) AS count
        FROM credit_transactions
        WHERE payment_status = 'Overdue'
    """).fetchone()

    overdue_transactions = overdue_result["count"]

    # --------------------------------------------------------
    # Paid Transactions
    # --------------------------------------------------------

    paid_result = conn.execute("""
        SELECT COUNT(*) AS count
        FROM credit_transactions
        WHERE payment_status = 'Paid'
    """).fetchone()

    paid_transactions = paid_result["count"]

    # --------------------------------------------------------
    # Total Transactions
    # --------------------------------------------------------

    transaction_result = conn.execute("""
        SELECT COUNT(*) AS total_transactions
        FROM credit_transactions
    """).fetchone()

    total_transactions = transaction_result["total_transactions"]

    # --------------------------------------------------------
    # Total Credited Items
    # --------------------------------------------------------

    item_result = conn.execute("""
        SELECT COUNT(*) AS total_items
        FROM credited_items
    """).fetchone()

    total_items = item_result["total_items"]

    # --------------------------------------------------------
    # Total Payment Records
    # --------------------------------------------------------

    payment_count_result = conn.execute("""
        SELECT COUNT(*) AS total_payment_records
        FROM payments
    """).fetchone()

    total_payment_records = payment_count_result["total_payment_records"]

    conn.close()

    return {
        "total_customers": total_customers,
        "total_transactions": total_transactions,
        "total_credit": total_credit,
        "total_payments": total_payments,
        "total_outstanding": total_outstanding,
        "pending_transactions": pending_transactions,
        "overdue_transactions": overdue_transactions,
        "paid_transactions": paid_transactions,
        "total_items": total_items,
        "total_payment_records": total_payment_records
    }