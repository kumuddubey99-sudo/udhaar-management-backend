from fastapi import FastAPI
import sqlite3

app = FastAPI()

DATABASE = "ums.db"

@app.get("/customers")
def get_customers():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    customers = conn.execute(
        "SELECT * FROM customers"
    ).fetchall()

    conn.close()

    return [dict(customer) for customer in customers]