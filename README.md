# 🧠 Xeno CRM - AI-Native Core API

The central intelligence and data orchestration layer for the Xeno Mini CRM. This backend powers natural language segmentation by translating marketer intent into database queries in real-time, while handling the asynchronous dispatch and receipt of messaging campaigns.

## ✨ Core Features
* **AI-Native Segmentation:** Integrates with local/cloud LLMs to convert natural language (e.g., *"Find all high-value customers from Chennai"*) into raw SQL queries.
* **Asynchronous Campaign Dispatch:** Processes large audience segments and fires non-blocking HTTP requests to the isolated Channel Service.
* **Real-Time Webhook Ingestion:** Receives asynchronous delivery receipts (Delivered, Opened, Failed) to update campaign metrics dynamically.
* **Simulated Data Ingestion:** Includes a zero-setup `setup_db.py` script to instantly scaffold a populated SQLite database with realistic customer and order data.

## 🛠 Tech Stack
* **Framework:** FastAPI (Python 3)
* **Database:** SQLite3
* **AI Engine:** Local `qwen2.5-coder:7b` (via Ollama) 

## 🚀 Quick Start

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Initialize the Database:**
   ```bash
   python setup_db.py
   ```
3. **Run the Server:**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

## 🏗 Architecture Note
This API is designed to work in tandem with the `xeno-channel-service`. Ensure the `CHANNEL_SERVICE_URL` in `main.py` is pointed to the correct instance (local or production) before launching a campaign.
