import sqlite3
import random
from datetime import datetime, timedelta

def setup_database():
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()

    # 1. Customers Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        phone TEXT,
        location TEXT,
        created_at TEXT
    )''')

    # 2. Orders Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        product_name TEXT,
        amount REAL,
        order_date TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )''')

    # 3. Campaigns Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        segment_query TEXT,
        message_template TEXT,
        status TEXT,
        created_at TEXT
    )''')

    # 4. Communications Log Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS communications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        customer_id INTEGER,
        channel TEXT,
        status TEXT,
        sent_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(campaign_id) REFERENCES campaigns(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )''')

    # Clear existing data if script is re-run
    cursor.execute('DELETE FROM communications')
    cursor.execute('DELETE FROM campaigns')
    cursor.execute('DELETE FROM orders')
    cursor.execute('DELETE FROM customers')

    # Generate Mock Data
    first_names = ["Anu", "Rahul", "Priya", "Vikram", "Sneha", "Karthik", "Neha", "Arjun", "Deepa", "Sanjay"]
    last_names = ["S", "Kumar", "Rao", "Menon", "Iyer", "Sharma", "Singh", "Das", "Patil", "Reddy"]
    locations = ["Chennai", "New Delhi", "Tiruchirappalli", "Mumbai", "Bangalore", "Hyderabad", "Kolkata"]
    products = ["Classic White Tee", "Denim Jacket", "Sneakers", "Sunglasses", "Coffee Beans - 1kg", "Espresso Machine", "Moisturizer", "Vitamin C Serum"]

    customers_data = []
    for i in range(1, 51):
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        email = f"user{i}@example.com"
        phone = f"+9198765{random.randint(10000, 99999)}"
        location = random.choice(locations)
        created_at = (datetime.now() - timedelta(days=random.randint(10, 365))).strftime("%Y-%m-%d")
        customers_data.append((name, email, phone, location, created_at))

    # The executemany() function inserts many records at a time, making the setup extremely efficient.
    cursor.executemany('''
    INSERT INTO customers (name, email, phone, location, created_at)
    VALUES (?, ?, ?, ?, ?)
    ''', customers_data)

    orders_data = []
    for _ in range(150):
        customer_id = random.randint(1, 50)
        product = random.choice(products)
        amount = round(random.uniform(500.0, 5000.0), 2)
        order_date = (datetime.now() - timedelta(days=random.randint(1, 300))).strftime("%Y-%m-%d")
        orders_data.append((customer_id, product, amount, order_date))

    cursor.executemany('''
    INSERT INTO orders (customer_id, product_name, amount, order_date)
    VALUES (?, ?, ?, ?)
    ''', orders_data)

    conn.commit()
    conn.close()
    print("Database 'crm_database.db' created and populated with 50 customers and 150 orders.")

if __name__ == "__main__":
    setup_database()