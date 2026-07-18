"""
This service handles order-related operations. It exposes a RESTful API for 
fetching orders, with built-in caching using Redis to reduce database load. 
If the cache misses, it queries the PostgreSQL database for the order data.

Flow: API Gateway -> Order Service (Flask API) -> Check Redis Cache (Hit/Miss) -> PostgreSQL Database (Order Data) -> Response
"""
from flask import Flask, jsonify
from contextlib import closing
import redis, psycopg2, os, json, logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# redis-py maintains its own internal connection pool by default,
# so module-level instantiation here is correct and safe.
redis_client = redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379'))


def get_db_conn():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )


@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "order-service"})


@app.route('/orders', methods=['GET'])
def get_orders():
    from flask import request
    cache_key = "orders_" + "_".join([f"{k}={v}" for k, v in sorted(request.args.items())])
    if not cache_key:
        cache_key = "all_orders"
        
    cached = redis_client.get(cache_key)
    if cached:
        logging.info(f"Cache HIT for orders {cache_key}")
        return jsonify(json.loads(cached))

    # contextlib.closing guarantees conn.close() is called even if an
    # exception is raised mid-query. Prevents connection exhaustion on
    # PostgreSQL's default max_connections=100.
    # NOTE: Per-request connect() is intentional for Phase 1 simplicity.
    # A connection pool is planned for Phase 2.
    try:
        with closing(get_db_conn()) as conn:
            with closing(conn.cursor()) as cur:
                query = "SELECT id, user_id, product, amount, status FROM orders WHERE 1=1"
                params = []

                if request.args.get('status'):
                    query += " AND status = %s"
                    params.append(request.args.get('status'))

                if request.args.get('user_id'):
                    query += " AND user_id = %s"
                    params.append(request.args.get('user_id'))

                cur.execute(query, params)
                orders = [
                    {"id": r[0], "user_id": r[1], "product": r[2],
                     "amount": float(r[3]), "status": r[4]}
                    for r in cur.fetchall()
                ]
        redis_client.setex(cache_key, 60, json.dumps(orders))  # Cache for 60s
        logging.info(f"Fetched {len(orders)} orders from DB, cached as {cache_key}")
        return jsonify(orders)
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": "database error"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)