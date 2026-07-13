from flask import Flask, jsonify, request
import redis, psycopg2, os, json, logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

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
    cache_key = "all_orders"
    cached = redis_client.get(cache_key)
    if cached:
        logging.info("Cache HIT for orders")
        return jsonify(json.loads(cached))

    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, product, amount, status FROM orders;")
        orders = [
            {"id": r[0], "user_id": r[1], "product": r[2], "amount": float(r[3]), "status": r[4]}
            for r in cur.fetchall()
        ]
        redis_client.setex(cache_key, 60, json.dumps(orders))  # Cache for 60s
        logging.info(f"Fetched {len(orders)} orders from DB, cached")
        return jsonify(orders)
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": "database error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)