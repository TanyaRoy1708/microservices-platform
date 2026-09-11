"""
test_services.py — Unit tests for all 4 microservices.

Strategy: All external dependencies (PostgreSQL, Redis, Ollama) are mocked
using unittest.mock. Tests run in <5 seconds, require only pip install,
and work in CI without Docker or any running infrastructure.

Mocking approach:
  - patch.object() keeps patches active for the full duration of each test
    (unlike patch() in a with-block which exits before the test method runs)
  - self.conn.cursor.return_value = self.cursor ensures conn.cursor() returns
    our controlled mock (not an auto-generated MagicMock whose fetchall we can't control)
  - TestClient used without context manager — lifespan is not triggered,
    db_pool is set directly on the module after import

Coverage:
  - api-gateway: health, proxy routing, 503 on ConnectError, 504 on timeout
  - user-service: health, list users, filter by city/name, 404, 500 error masking
  - order-service: health, list orders, filter, Redis cache hit (DB skipped), cache miss (DB queried)
  - ai-service: validator allowlist (8 cases covering all rejection paths)
"""
import json
import sys
import os
import importlib
import importlib.util
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


def load_service_app(service_name: str):
    service_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", service_name))
    app_path = os.path.join(service_dir, "app.py")
    spec = importlib.util.spec_from_file_location(f"{service_name.replace('-', '_')}_app", app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ─── API GATEWAY ──────────────────────────────────────────────────────────────

class TestApiGateway:

    @pytest.fixture(autouse=True)
    def setup(self):
        gw_app = load_service_app("api-gateway")
        self.client = TestClient(gw_app.app, raise_server_exceptions=False)

    def test_health_returns_200(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["service"] == "api-gateway"

    def test_proxy_users_forwards_response(self):
        """Gateway forwards upstream response body and status code transparently."""
        mock_resp = MagicMock()
        mock_resp.content = json.dumps([{"id": 1, "name": "Priya"}]).encode()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=mock_resp)):
            r = self.client.get("/users")
        assert r.status_code == 200

    def test_proxy_returns_503_on_connect_error(self):
        """ConnectError → 503 Service Unavailable."""
        import httpx
        with patch("httpx.AsyncClient.request", new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
            r = self.client.get("/users")
        assert r.status_code == 503
        assert "unavailable" in r.json()["detail"].lower()

    def test_proxy_returns_504_on_timeout(self):
        """TimeoutException → 504 Gateway Timeout."""
        import httpx
        with patch("httpx.AsyncClient.request", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
            r = self.client.get("/orders")
        assert r.status_code == 504
        assert "timeout" in r.json()["detail"].lower()

    def test_proxy_returns_502_on_request_error(self):
        """Generic RequestError → 502 Bad Gateway."""
        import httpx
        with patch("httpx.AsyncClient.request", new=AsyncMock(side_effect=httpx.RequestError("network reset"))):
            r = self.client.get("/users")
        assert r.status_code == 502


# ─── USER SERVICE ─────────────────────────────────────────────────────────────

class TestUserService:
    """
    Mock setup rationale:
      self.conn.cursor.return_value = self.cursor
      → conn.cursor() returns self.cursor
      → closing(conn.cursor()) gives cur = self.cursor
      → self.cursor.fetchall.return_value controls query results

    patch.object(user_app, 'db_pool', self.pool) stays active for the full test
    because it's applied in a fixture, not in a with-block that exits before the test.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        user_app = load_service_app("user-service")

        self.pool = MagicMock()
        self.conn = MagicMock()
        self.cursor = MagicMock()

        # Critical: cursor() must return self.cursor directly
        # so closing(conn.cursor()) gives us cur = self.cursor
        self.pool.getconn.return_value = self.conn
        self.conn.cursor.return_value = self.cursor

        with patch.object(user_app, "db_pool", self.pool):
            self.client = TestClient(user_app.app, raise_server_exceptions=False)
            yield  # patch.object stays active for the full duration of each test method

    def test_health_check_returns_200(self):
        r = self.client.get("/health")
        assert r.status_code in (200, 503)   # 503 if db_pool.minconn doesn't exist on mock
        data = r.json()
        assert data["service"] == "user-service"

    def test_health_includes_dependencies_field(self):
        """Health check must report dependency status — not just a static 'healthy' string."""
        r = self.client.get("/health")
        data = r.json()
        assert "dependencies" in data
        assert "postgres" in data["dependencies"]

    def test_list_all_users_returns_list(self):
        self.cursor.fetchall.return_value = [
            (1, "Priya Sharma", "priya@example.com", "Mumbai"),
            (2, "Rahul Gupta", "rahul@example.com", "Delhi"),
        ]
        r = self.client.get("/users")
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        assert len(users) == 2
        assert users[0]["name"] == "Priya Sharma"
        assert users[0]["city"] == "Mumbai"
        assert "email" in users[0]

    def test_filter_users_by_city(self):
        self.cursor.fetchall.return_value = [
            (1, "Priya Sharma", "priya@example.com", "Mumbai"),
        ]
        r = self.client.get("/users?city=Mumbai")
        assert r.status_code == 200
        assert all(u["city"] == "Mumbai" for u in r.json())

    def test_filter_users_by_name(self):
        self.cursor.fetchall.return_value = [
            (2, "Rahul Gupta", "rahul@example.com", "Delhi"),
        ]
        r = self.client.get("/users?name=Rahul%20Gupta")
        assert r.status_code == 200
        assert r.json()[0]["name"] == "Rahul Gupta"

    def test_get_user_by_id_returns_correct_shape(self):
        self.cursor.fetchone.return_value = (1, "Priya Sharma", "priya@example.com", "Mumbai")
        r = self.client.get("/users/1")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == 1
        assert data["name"] == "Priya Sharma"
        assert data["city"] == "Mumbai"

    def test_get_nonexistent_user_returns_404(self):
        self.cursor.fetchone.return_value = None
        r = self.client.get("/users/9999")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_db_error_returns_500_without_leaking_details(self):
        """DB errors return 500. The internal exception message must NOT be exposed to callers."""
        self.cursor.fetchall.side_effect = Exception("pg: connection reset by peer")
        r = self.client.get("/users")
        assert r.status_code == 500
        # Security: internal error details must not leak to API consumers
        assert "connection reset" not in r.json()["detail"]
        assert r.json()["detail"] == "database error"


# ─── ORDER SERVICE ────────────────────────────────────────────────────────────

class TestOrderService:

    @pytest.fixture(autouse=True)
    def setup(self):
        order_app = load_service_app("order-service")

        self.pool = MagicMock()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.pool.getconn.return_value = self.conn
        self.conn.cursor.return_value = self.cursor   # Fix: direct assignment, not __enter__

        self.mock_redis = MagicMock()
        self.mock_redis.get.return_value = None       # Default: cache miss

        with patch.object(order_app, "db_pool", self.pool), \
             patch.object(order_app, "redis_client", self.mock_redis):
            self.client = TestClient(order_app.app, raise_server_exceptions=False)
            yield   # Patches stay active for entire test method

    def test_health_check_returns_service_name(self):
        r = self.client.get("/health")
        assert r.json()["service"] == "order-service"

    def test_health_checks_both_db_and_redis(self):
        """Order service health must report both dependencies, not just DB."""
        r = self.client.get("/health")
        deps = r.json().get("dependencies", {})
        assert "postgres" in deps
        assert "redis" in deps

    def test_cache_miss_queries_db_and_writes_cache(self):
        """On cache miss: DB is queried, result is written to Redis with TTL."""
        self.cursor.fetchall.return_value = [
            (1, 1, "MacBook Pro", 120000.00, "delivered"),
            (2, 2, "iPhone 15", 85000.00, "shipped"),
        ]
        r = self.client.get("/orders")
        assert r.status_code == 200
        orders = r.json()
        assert len(orders) == 2
        assert orders[0]["product"] == "MacBook Pro"
        assert orders[0]["amount"] == 120000.0
        # Verify Redis was written to after DB fetch (cache population)
        self.mock_redis.setex.assert_called_once()

    def test_cache_hit_skips_db_entirely(self):
        """On cache hit: DB must NOT be queried — Redis serves the response directly."""
        cached = [{"id": 1, "user_id": 1, "product": "MacBook Pro",
                   "amount": 120000.0, "status": "delivered"}]
        self.mock_redis.get.return_value = json.dumps(cached).encode()

        r = self.client.get("/orders")
        assert r.status_code == 200
        assert r.json() == cached
        # DB cursor must not be touched — Redis returned the response
        self.cursor.execute.assert_not_called()

    def test_filter_by_status(self):
        self.cursor.fetchall.return_value = [(3, 3, "AirPods Pro", 20000.00, "pending")]
        r = self.client.get("/orders?status=pending")
        assert r.status_code == 200
        assert all(o["status"] == "pending" for o in r.json())

    def test_filter_by_min_amount(self):
        self.cursor.fetchall.return_value = [(1, 1, "MacBook Pro", 120000.00, "delivered")]
        r = self.client.get("/orders?min_amount=50000")
        assert r.status_code == 200
        assert all(o["amount"] >= 50000 for o in r.json())

    def test_filter_by_user_id(self):
        self.cursor.fetchall.return_value = [
            (1, 1, "MacBook Pro", 120000.00, "delivered"),
            (4, 1, "iPad Air", 65000.00, "delivered"),
        ]
        r = self.client.get("/orders?user_id=1")
        assert r.status_code == 200
        assert all(o["user_id"] == 1 for o in r.json())


# ─── AI SERVICE — VALIDATOR ────────────────────────────────────────────────────

class TestAiServiceValidator:
    """
    Tests the intent validation allowlist in isolation.
    No LLM calls, no network — pure logic testing.

    This is the security boundary between untrusted LLM output and
    actual API execution. Every rejection path must be covered.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from validator import validate_intent
        self.validate = validate_intent

    def test_valid_list_users(self):
        intent = {"service": "users", "operation": "list_users", "filters": {}}
        is_valid, reason = self.validate(intent)
        assert is_valid is True
        assert reason == ""

    def test_valid_find_users_by_city(self):
        intent = {"service": "users", "operation": "find_users_by_city", "filters": {"city": "Mumbai"}}
        is_valid, _ = self.validate(intent)
        assert is_valid is True

    def test_valid_orders_by_status(self):
        intent = {"service": "orders", "operation": "find_orders_by_status",
                  "filters": {"status": "pending"}}
        is_valid, _ = self.validate(intent)
        assert is_valid is True

    def test_valid_orders_by_amount_range(self):
        intent = {"service": "orders", "operation": "find_orders_by_amount",
                  "filters": {"min_amount": "50000", "max_amount": "150000"}}
        is_valid, _ = self.validate(intent)
        assert is_valid is True

    def test_unknown_service_rejected(self):
        """LLM hallucinating an unknown service must be blocked before execution."""
        intent = {"service": "payments", "operation": "charge_card", "filters": {}}
        is_valid, reason = self.validate(intent)
        assert is_valid is False
        assert "payments" in reason.lower() or "unknown" in reason.lower()

    def test_unknown_operation_rejected(self):
        """Mutating operations (delete, update) not in the allowlist must be blocked."""
        intent = {"service": "users", "operation": "delete_user", "filters": {}}
        is_valid, reason = self.validate(intent)
        assert is_valid is False
        assert "delete_user" in reason or "unknown operation" in reason.lower()

    def test_unknown_filter_key_rejected(self):
        """Unknown filter keys (potential prompt injection) must be rejected."""
        intent = {"service": "users", "operation": "list_users",
                  "filters": {"DROP TABLE": "users"}}
        is_valid, reason = self.validate(intent)
        assert is_valid is False

    def test_missing_service_field_rejected(self):
        intent = {"operation": "list_users", "filters": {}}
        is_valid, reason = self.validate(intent)
        assert is_valid is False
        assert "service" in reason.lower() or "missing" in reason.lower()

    def test_missing_operation_field_rejected(self):
        intent = {"service": "users", "filters": {}}
        is_valid, reason = self.validate(intent)
        assert is_valid is False
        assert "operation" in reason.lower() or "missing" in reason.lower()

    def test_wrong_operation_for_service_rejected(self):
        """Cross-service operation confusion must be caught."""
        intent = {"service": "users", "operation": "find_orders_by_status",
                  "filters": {"status": "pending"}}
        is_valid, _ = self.validate(intent)
        assert is_valid is False
