"""
This service provides an AI query interface. It receives natural language 
requests, uses a local Ollama LLM to extract the user's intent, and then 
orchestrates calls to other internal microservices to fulfill the request.

Flow: API Gateway -> AI Service (FastAPI) -> Ollama (LLM prompt) -> Extracted Intent -> Orchestrate internal APIs -> Response
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx, os, json, logging
from prompts import INTENT_EXTRACTION_PROMPT
from validator import validate_intent

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="AI Query Service")

OLLAMA_URL = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3.2:1b')
USER_SVC_URL = os.environ.get('USER_SERVICE_URL', 'http://user-service:5001')
ORDER_SVC_URL = os.environ.get('ORDER_SERVICE_URL', 'http://order-service:5002')

class QueryRequest(BaseModel):
    query: str

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ai-service", "version": "2.0"}

async def call_llm(prompt: str, user_query: str) -> dict:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user_query}],
        "stream": False, "options": {"temperature": 0.0}
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
    
    raw = r.json()['message']['content'].strip()
    if raw.startswith("```"): raw = raw.split("```")[1].replace("json", "").strip()
    return json.loads(raw)

@app.post("/ai/query")
async def ai_query(request: QueryRequest):
    # 1. Extract Intent
    try:
        intent = await call_llm(INTENT_EXTRACTION_PROMPT, request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {e}")

    # 2. Validate Intent
    is_valid, reason = validate_intent(intent)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid intent: {reason}")

    # 3. Execute Service Call
    filters = intent.get("filters", {})
    async with httpx.AsyncClient(timeout=10) as client:
        if intent["service"] == "users":
            r = await client.get(f"{USER_SVC_URL}/users", params=filters)
            results = r.json()
            
        elif intent["service"] == "orders":
            # Handle cross-service lookup if user_name is provided
            if "user_name" in filters:
                u = await client.get(f"{USER_SVC_URL}/users", params={"name": filters.pop("user_name")})
                if not u.json(): return {"intent": intent, "results": [], "note": "User not found"}
                filters["user_id"] = u.json()[0]["id"]
                
            r = await client.get(f"{ORDER_SVC_URL}/orders", params=filters)
            results = r.json()

    return {"intent": intent, "results": results}