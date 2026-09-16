# ============================================================
# CREDITED ITEM MODELS
# ============================================================

class ItemCreate(BaseModel):
    transaction_id: str
    item_name: str
    quantity: int
    unit_price: float
    credited_date: str


class ItemUpdate(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    credited_date: Optional[str] = None
# ============================================================
# GET ALL CREDITED ITEMS
# ============================================================

@app.get("/items")
def get_items():

    conn = get_connection()

    items = conn.execute("""
        SELECT
            i.item_id,
            i.transaction_id,
            i.item_name,
            i.quantity,
            i.unit_price,
            i.subtotal,
            i.credited_date
        FROM credited_items i
        ORDER BY i.credited_date DESC
    """).fetchall()

    conn.close()

    return [dict(row) for row in items]
# ============================================================
# ADD CREDITED ITEM
# ============================================================

@app.post("/items")
def add_item(item: ItemCreate):

    conn = get_connection()

    # Check transaction exists
    transaction = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (item.transaction_id,)).fetchone()

    if not transaction:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    # Validate item name
    if not item.item_name.strip():
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Item name cannot be empty"
        )

    # Validate quantity
    if item.quantity <= 0:
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    # Validate unit price
    if item.unit_price <= 0:
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Unit price must be greater than 0"
        )

    # Calculate subtotal automatically
    subtotal = item.quantity * item.unit_price

    # Generate Item ID
    last_item = conn.execute("""
        SELECT item_id
        FROM credited_items
        ORDER BY rowid DESC
        LIMIT 1
    """).fetchone()

    if last_item:

        last_id = last_item["item_id"]

        try:
            number = int(last_id.replace("I", ""))
            new_number = number + 1

        except ValueError:
            new_number = 1

    else:
        new_number = 1

    item_id = f"I{new_number:03d}"

    # Insert item
    conn.execute("""
        INSERT INTO credited_items (
            item_id,
            transaction_id,
            item_name,
            quantity,
            unit_price,
            subtotal,
            credited_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        item_id,
        item.transaction_id,
        item.item_name.strip(),
        item.quantity,
        item.unit_price,
        subtotal,
        item.credited_date
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Credited item added successfully",
        "item_id": item_id,
        "subtotal": subtotal
    }
# ============================================================
# GET ONE CREDITED ITEM
# ============================================================

@app.get("/items/{item_id}")
def get_item(item_id: str):

    conn = get_connection()

    item = conn.execute("""
        SELECT
            i.item_id,
            i.transaction_id,
            i.item_name,
            i.quantity,
            i.unit_price,
            i.subtotal,
            i.credited_date
        FROM credited_items i
        WHERE i.item_id = ?
    """, (item_id,)).fetchone()

    conn.close()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Credited item not found"
        )

    return dict(item)
# ============================================================
# GET ITEMS OF A TRANSACTION
# ============================================================

@app.get("/transactions/{transaction_id}/items")
def get_transaction_items(transaction_id: str):

    conn = get_connection()

    # Check transaction
    transaction = conn.execute("""
        SELECT transaction_id
        FROM credit_transactions
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if not transaction:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    items = conn.execute("""
        SELECT
            item_id,
            transaction_id,
            item_name,
            quantity,
            unit_price,
            subtotal,
            credited_date
        FROM credited_items
        WHERE transaction_id = ?
        ORDER BY credited_date DESC
    """, (transaction_id,)).fetchall()

    conn.close()

    return [dict(row) for row in items]
# ============================================================
# UPDATE CREDITED ITEM
# ============================================================

@app.put("/items/{item_id}")
def update_item(
    item_id: str,
    item: ItemUpdate
):

    conn = get_connection()

    existing = conn.execute("""
        SELECT *
        FROM credited_items
        WHERE item_id = ?
    """, (item_id,)).fetchone()

    if not existing:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Credited item not found"
        )

    # Keep old values if new values are not provided

    item_name = (
        item.item_name
        if item.item_name is not None
        else existing["item_name"]
    )

    quantity = (
        item.quantity
        if item.quantity is not None
        else existing["quantity"]
    )

    unit_price = (
        item.unit_price
        if item.unit_price is not None
        else existing["unit_price"]
    )

    credited_date = (
        item.credited_date
        if item.credited_date is not None
        else existing["credited_date"]
    )

    # Validation

    if not item_name.strip():
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Item name cannot be empty"
        )

    if quantity <= 0:
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    if unit_price <= 0:
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Unit price must be greater than 0"
        )

    # Recalculate subtotal
    subtotal = quantity * unit_price

    conn.execute("""
        UPDATE credited_items
        SET
            item_name = ?,
            quantity = ?,
            unit_price = ?,
            subtotal = ?,
            credited_date = ?
        WHERE item_id = ?
    """, (
        item_name.strip(),
        quantity,
        unit_price,
        subtotal,
        credited_date,
        item_id
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Credited item updated successfully",
        "item_id": item_id,
        "subtotal": subtotal
    }
# ============================================================
# DELETE CREDITED ITEM
# ============================================================

@app.delete("/items/{item_id}")
def delete_item(item_id: str):

    conn = get_connection()

    existing = conn.execute("""
        SELECT item_id
        FROM credited_items
        WHERE item_id = ?
    """, (item_id,)).fetchone()

    if not existing:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Credited item not found"
        )

    conn.execute("""
        DELETE FROM credited_items
        WHERE item_id = ?
    """, (item_id,))

    conn.commit()
    conn.close()

    return {
        "message": "Credited item deleted successfully",
        "item_id": item_id
    }




