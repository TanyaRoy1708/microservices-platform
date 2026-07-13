from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx, os, logging

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="AI Query Service", version="1.0")

OLLAMA_URL     = os.environ.get('OLLAMA_BASE_URL',   'http://ollama:11434')
USER_SVC_URL   = os.environ.get('USER_SERVICE_URL',  'http://user-service:5001')
ORDER_SVC_URL  = os.environ.get('ORDER_SERVICE_URL', 'http://order-service:5002')

class QueryRequest(BaseModel):
    query: str
    context_limit: int = 5

SYSTEM_PROMPT = """You are a helpful assistant for a microservices platform.
You receive a natural language query and structured data from user and order services.
Your job is to extract relevant information and respond concisely.
Always respond in JSON format: {"answer": "...", "relevant_records": [...]}"""

@app.get("/health")
async def health():
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            ollama_ok = r.status_code == 200
        except Exception:
            ollama_ok = False
    return {"status": "healthy", "service": "ai-service", "ollama_connected": ollama_ok}

@app.post("/ai/query")
async def ai_query(request: QueryRequest):
    """Natural language query endpoint backed by local LLM (Ollama)."""
    async with httpx.AsyncClient(timeout=30) as client:
        users_r  = await client.get(f"{USER_SVC_URL}/users")
        orders_r = await client.get(f"{ORDER_SVC_URL}/orders")
        users  = users_r.json()  if users_r.status_code  == 200 else []
        orders = orders_r.json() if orders_r.status_code == 200 else []

        context = f"""
Available Data:
USERS (first {request.context_limit}): {users[:request.context_limit]}
ORDERS (first {request.context_limit}): {orders[:request.context_limit]}

User Query: {request.query}
"""
        llm_payload = {
            "model": os.environ.get('OLLAMA_MODEL', 'llama3.2:1b'),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": context}
            ],
            "stream": False,
            "options": {"temperature": 0.1}
        }

        try:
            llm_response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json=llm_payload,
                timeout=60
            )
            result = llm_response.json()
            answer = result['message']['content']
            logging.info(f"LLM query processed: '{request.query[:50]}...'")
            return {"query": request.query, "ai_response": answer, "model": llm_payload["model"]}

        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="AI service timeout - model may be loading")