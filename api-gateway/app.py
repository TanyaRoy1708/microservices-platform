from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx, os, logging

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="API Gateway", version="1.0")

USER_SVC  = os.environ.get('USER_SERVICE_URL',  'http://user-service:5001')
ORDER_SVC = os.environ.get('ORDER_SERVICE_URL', 'http://order-service:5002')
AI_SVC    = os.environ.get('AI_SERVICE_URL',    'http://ai-service:5003')

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "api-gateway"}

@app.api_route("/users{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_users(path: str, request: Request):
    return await _proxy(f"{USER_SVC}/users{path}", request)

@app.api_route("/orders{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orders(path: str, request: Request):
    return await _proxy(f"{ORDER_SVC}/orders{path}", request)

@app.post("/ai/query")
async def proxy_ai(request: Request):
    return await _proxy(f"{AI_SVC}/ai/query", request)

async def _proxy(url: str, request: Request):
    async with httpx.AsyncClient(timeout=65) as client:
        try:
            body = await request.body()
            r = await client.request(
                method=request.method, url=url,
                content=body, headers=dict(request.headers)
            )
            return Response(content=r.content, status_code=r.status_code,
                            media_type=r.headers.get("content-type"))
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail=f"Upstream service unavailable: {url}")