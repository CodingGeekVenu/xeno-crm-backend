from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import requests
import json
import os
from google import genai

app = FastAPI(title="Xeno AI-Native Mini CRM")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows your GitHub Pages domain to talk to Render
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Gemini via Environment Variable
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
# We will set this up in the next step
CHANNEL_SERVICE_URL = "https://xeno-channel-service-9lsx.onrender.com/send" 

# --- Pydantic Models for API Validation ---
class ChatRequest(BaseModel):
    prompt: str

class RewriteRequest(BaseModel):
    text: str

class CampaignRequest(BaseModel):
    name: str
    message_template: str
    customer_ids: List[int]
    channel: str = "whatsapp"

class WebhookPayload(BaseModel):
    communication_id: int
    status: str

# --- Database Helper ---
def get_db_connection():
    conn = sqlite3.connect('crm_database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- The AI Engine ---
def generate_sql_from_prompt(prompt: str) -> str:
    """Uses qwen2.5-coder to translate natural language to SQL."""
    schema = """
    Table: customers (id INTEGER, name TEXT, email TEXT, phone TEXT, location TEXT, created_at TEXT)
    Table: orders (id INTEGER, customer_id INTEGER, product_name TEXT, amount REAL, order_date TEXT)
    """
    
    system_prompt = f"""
    You are an expert SQL developer. Given the schema below, write a raw SQLite query to satisfy the user's request.
    Schema:
    {schema}
    
    Rules:
    1. Return ONLY the raw SQL query. No markdown formatting, no backticks, no explanations.
    2. Always SELECT DISTINCT customers.id, customers.name, customers.email, customers.location
    3. Use standard SQLite syntax.
    4. CRITICAL: If the user's request is just a greeting (e.g., "hi", "hello") or completely unrelated to finding customers, return EXACTLY the string "INVALID_PROMPT" and nothing else.
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=f"{system_prompt}\n\nUser Request: {prompt}"
        )
        raw_sql = response.text.strip()
        
        if "```sql" in raw_sql:
            raw_sql = raw_sql.split("```sql")[1].split("```")[0].strip()
        elif "```" in raw_sql:
            raw_sql = raw_sql.split("```")[1].split("```")[0].strip()
            
        return raw_sql.rstrip(";")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")


# --- API Routes ---

# --- Additional Pydantic Models ---
class Customer(BaseModel):
    name: str
    email: str
    phone: str
    location: str

class Order(BaseModel):
    customer_id: int
    product_name: str
    amount: float

# --- Data Ingestion API Routes ---
@app.get("/api/customers")
async def get_customers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers ORDER BY id DESC LIMIT 100")
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return customers

@app.post("/api/customers", status_code=201)
async def create_customer(customer: Customer):
    """Simulates webhook ingestion from a Shopify/POS system"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO customers (name, email, phone, location, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (customer.name, customer.email, customer.phone, customer.location)
    )
    customer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"message": "Customer ingested", "id": customer_id}

@app.post("/api/orders", status_code=201)
async def create_order(order: Order):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (customer_id, product_name, amount, order_date) VALUES (?, ?, ?, datetime('now'))",
        (order.customer_id, order.product_name, order.amount)
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"message": "Order ingested", "id": order_id}

@app.post("/api/segment")
async def create_segment(request: ChatRequest):
    """AI-Native Segmentation: Chat to Audience"""
    sql_query = generate_sql_from_prompt(request.prompt)
    
    if sql_query == "INVALID_PROMPT":
         raise HTTPException(status_code=400, detail="I am an AI Segmentation Builder. Please ask me to find a specific audience.")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        conn.close()
        
        customers = [dict(row) for row in rows]
        return {
            "query_used": sql_query,
            "audience_size": len(customers),
            "customers": customers
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database execution failed. SQL: {sql_query}. Error: {str(e)}")

@app.post("/api/campaigns")
async def launch_campaign(request: CampaignRequest, background_tasks: BackgroundTasks):
    """Saves the campaign and pushes to the Stubbed Channel Service."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create Campaign
    cursor.execute(
        "INSERT INTO campaigns (name, message_template, status, created_at) VALUES (?, ?, ?, datetime('now'))",
        (request.name, request.message_template, "Sending")
    )
    campaign_id = cursor.lastrowid
    
    # 2. Log Pending Communications & Dispatch
    communications_created = 0
    for customer_id in request.customer_ids:
        cursor.execute(
            "INSERT INTO communications (campaign_id, customer_id, channel, status, sent_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (campaign_id, customer_id, request.channel, "Pending")
        )
        comm_id = cursor.lastrowid
        communications_created += 1
        
        # In a real system, we'd use a message queue (RabbitMQ/Kafka) here.
        # For this scope, we fire a fire-and-forget HTTP request to our stub service.
        payload = {
            "communication_id": comm_id,
            "customer_id": customer_id,
            "message": request.message_template,
            "channel": request.channel,
            "webhook_url": os.environ.get("CRM_WEBHOOK_URL", "https://xeno-crm-backend-itr8.onrender.com/api/webhooks/channel")
        }
        
        # Fire in background so the CRM API doesn't block
        def dispatch_to_channel(data):
            try:
                response = requests.post(CHANNEL_SERVICE_URL, json=data, timeout=5)
                # Check if the channel service actually accepted it
                if response.status_code != 202:
                    print(f"DEBUG: Channel Service rejected request! Status: {response.status_code}, Body: {response.text}")
            except Exception as e:
                print(f"DEBUG: Critical failure dispatching to Channel Service: {str(e)}")

        background_tasks.add_task(dispatch_to_channel, payload)

    conn.commit()
    conn.close()
    
    return {"message": "Campaign launched", "campaign_id": campaign_id, "messages_queued": communications_created}

@app.post("/api/webhooks/channel")
async def channel_receipt(payload: WebhookPayload):
    """The vital callback loop from the Channel Service."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE communications SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (payload.status, payload.communication_id)
    )
    
    conn.commit()
    conn.close()
    return {"status": "acknowledged"}

@app.post("/api/rewrite")
async def rewrite_message(request: RewriteRequest):
    """Real AI Rewrite using the local LLM."""
    system_prompt = "You are an expert marketing copywriter. Rewrite the following message to be more engaging, conversational, and conversion-focused. Keep it under 3 sentences. Do not include any explanations or markdown, just return the rewritten text."
    
    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=f"{system_prompt}\n\nOriginal: {request.text}"
        )
        return {"rewritten_text": response.text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")

# --- Basic Analytics Route ---
@app.get("/api/analytics")
async def get_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, COUNT(*) as count FROM communications GROUP BY status")
    stats = {row['status']: row['count'] for row in cursor.fetchall()}
    
    conn.close()
    return stats