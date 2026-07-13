from flask import Flask, jsonify
from contextlib import closing
import psycopg2, os, logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)


def get_db_conn():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )


@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "user-service", "version": "1.0"})


@app.route('/users', methods=['GET'])
def get_users():
    # contextlib.closing guarantees conn.close() is called even if an
    # exception is raised mid-query. Prevents connection exhaustion on
    # PostgreSQL's default max_connections=100.
    # NOTE: Per-request connect() is intentional for Phase 1 simplicity.
    # A ThreadedConnectionPool / SQLAlchemy pool is planned for Phase 2
    # when throughput requirements are established.
    try:
        with closing(get_db_conn()) as conn:
            with closing(conn.cursor()) as cur:
                cur.execute("SELECT id, name, email, city FROM users;")
                users = [
                    {"id": r[0], "name": r[1], "email": r[2], "city": r[3]}
                    for r in cur.fetchall()
                ]
        logging.info(f"Fetched {len(users)} users")
        return jsonify(users)
    except Exception as e:
        logging.error(f"DB error: {e}")
        return jsonify({"error": "database error"}), 500


@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    try:
        with closing(get_db_conn()) as conn:
            with closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT id, name, email, city FROM users WHERE id = %s;",
                    (user_id,)
                )
                row = cur.fetchone()
        if not row:
            return jsonify({"error": "user not found"}), 404
        return jsonify({"id": row[0], "name": row[1], "email": row[2], "city": row[3]})
    except Exception as e:
        logging.error(f"DB error for user {user_id}: {e}")
        return jsonify({"error": "database error"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
