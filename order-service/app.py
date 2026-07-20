"""
This service handles order-related operations. It exposes a RESTful API for 
fetching orders, with built-in caching using Redis to reduce database load. 
If the cache misses, it queries the PostgreSQL database for the order data.

Flow: API Gateway -> Order Service (FastAPI) -> Check Redis Cache (Hit/Miss) -> PostgreSQL Database (Order Data) -> Response
"""
from fastapi import FastAPI, HTTPException, Request, Query
from contextlib import closing, contextmanager
import redis, psycopg2, os, json, logging
from psycopg2 import pool
from typing import Optional

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Order Service", version="1.0")

# redis-py maintains its own internal connection pool by default,
# so module-level instantiation here is correct and safe.
redis_client = redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379'))


db_pool = None

@app.on_event("startup")
def startup_event():
    global db_pool
    db_pool = pool.SimpleConnectionPool(
        1, 20,
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )

@app.on_event("shutdown")
def shutdown_event():
    if db_pool:
        db_pool.closeall()

@contextmanager
def get_db_conn():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


@app.get('/health')
def health():
    return {"status": "healthy", "service": "order-service"}


@app.get('/orders')
def get_orders(
    request: Request,
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None)
):
    cache_key = "orders_" + "_".join([f"{k}={v}" for k, v in sorted(request.query_params.items())])
    if cache_key == "orders_":
        cache_key = "all_orders"
        
    cached = redis_client.get(cache_key)
    if cached:
        logging.info(f"Cache HIT for orders {cache_key}")
        return json.loads(cached)

    try:
        with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                query = "SELECT id, user_id, product, amount, status FROM orders WHERE 1=1"
                params = []

                if status:
                    query += " AND status = %s"
                    params.append(status)

                if user_id:
                    query += " AND user_id = %s"
                    params.append(user_id)

                cur.execute(query, params)
                orders = [
                    {"id": r[0], "user_id": r[1], "product": r[2],
                     "amount": float(r[3]), "status": r[4]}
                    for r in cur.fetchall()
                ]
        redis_client.setex(cache_key, 60, json.dumps(orders))  # Cache for 60s
        logging.info(f"Fetched {len(orders)} orders from DB, cached as {cache_key}")
        return orders
    except Exception as e:
        logging.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="database error")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5002)