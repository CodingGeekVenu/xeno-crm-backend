from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import requests
import json

app = FastAPI(title="Xeno AI-Native Mini CRM")

# Configuration for Local Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
# We will set this up in the next step
CHANNEL_SERVICE_URL = "http://localhost:8001/send" 

# --- Pydantic Models for API Validation ---
class ChatRequest(BaseModel):
    prompt: str

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
    """

    payload = {
        "model": MODEL_NAME,
        "prompt": f"{system_prompt}\n\nUser Request: {prompt}",
        "stream": False,
        "options": {
            "temperature": 0.0 # Keep it strictly factual for coding
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        raw_sql = response.json().get("response", "").strip()
        
        # Clean up any accidental markdown the model might output despite instructions
        if raw_sql.startswith("```sql"):
            raw_sql = raw_sql[6:-3].strip()
        
        return raw_sql
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")


# --- API Routes ---

@app.post("/api/segment")
async def create_segment(request: ChatRequest):
    """AI-Native Segmentation: Chat to Audience"""
    sql_query = generate_sql_from_prompt(request.prompt)
    
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
            "webhook_url": "http://localhost:8000/api/webhooks/channel"
        }
        
        # Fire in background so the CRM API doesn't block
        def dispatch_to_channel(data):
            try:
                requests.post(CHANNEL_SERVICE_URL, json=data, timeout=2)
            except requests.exceptions.RequestException:
                pass # Ignore failures for the scope of this mock dispatch

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

# --- Basic Analytics Route ---
@app.get("/api/analytics")
async def get_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, COUNT(*) as count FROM communications GROUP BY status")
    stats = {row['status']: row['count'] for row in cursor.fetchall()}
    
    conn.close()
    return stats