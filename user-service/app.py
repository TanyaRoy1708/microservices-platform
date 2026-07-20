"""
This service manages user-related operations. It exposes a RESTful API to 
fetch user data and connects directly to a PostgreSQL database to query 
the underlying user records.

Flow: API Gateway -> User Service (FastAPI) -> PostgreSQL Database (User Data) -> Response
"""
from fastapi import FastAPI, HTTPException, Query
from contextlib import closing, contextmanager
import psycopg2, os, logging
from psycopg2 import pool

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="User Service", version="1.0")


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
    return {"status": "healthy", "service": "user-service", "version": "1.0"}


@app.get('/users')
def get_users(
    name: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    email: Optional[str] = Query(None)
):
    try:
        with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                query = "SELECT id, name, email, city FROM users WHERE 1=1"
                params = []

                if name:
                    query += " AND LOWER(name) = LOWER(%s)"
                    params.append(name)

                if city:
                    query += " AND LOWER(city) = LOWER(%s)"
                    params.append(city)

                if email:
                    query += " AND email = %s"
                    params.append(email)

                cur.execute(query, params)
                users = [
                    {"id": r[0], "name": r[1], "email": r[2], "city": r[3]}
                    for r in cur.fetchall()
                ]
        logging.info(f"Fetched {len(users)} users")
        return users
    except Exception as e:
        logging.error(f"DB error: {e}")
        raise HTTPException(status_code=500, detail="database error")


@app.get('/users/{user_id}')
def get_user(user_id: int):
    try:
        with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT id, name, email, city FROM users WHERE id = %s;",
                    (user_id,)
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        return {"id": row[0], "name": row[1], "email": row[2], "city": row[3]}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"DB error for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="database error")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5001)
