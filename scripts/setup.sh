#!/bin/bash
# scripts/setup.sh One-command platform setup
set -euo pipefail

echo "Setting up microservices and AI platform..."

# Check prerequisites
command -v docker  >/dev/null || { echo "Docker not found"; exit 1; }
command -v python3 >/dev/null || { echo "Python not found"; exit 1; }

# Create .env if missing
[ ! -f .env ] && cp .env.example .env && echo "Created .env from template"
echo "Reminder: Edit .env with real passwords before production!"

# Start infrastructure first
echo "Starting PostgreSQL and Redis..."
docker compose up postgres redis -d
until docker compose exec postgres pg_isready -U "${DB_USER:-appuser}"; do
    echo "  Waiting for PostgreSQL..."; sleep 2
done
echo "PostgreSQL ready"

# Start Ollama and pull model
echo "Starting Ollama..."
docker compose up ollama -d
echo "Pulling AI model (this takes 2-3 mins on first run)..."
docker compose run --rm ollama-model-pull
echo "Model pulled and ready"

# Build and start all services
echo "Building and starting all services..."
docker compose up --build -d

echo "Waiting 15s for services to stabilize..."
sleep 15

# Health check all services
echo ""
echo "Running health checks..."
for port_path in "8000/health" "5001/health" "5002/health" "5003/health"; do
    response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port_path}")
    if [ "$response" == "200" ]; then
        echo "  http://localhost/${port_path}"
    else
        echo "  http://localhost/${port_path} got HTTP $response"
    fi
done

# Test AI endpoint
echo ""
echo "Testing AI query endpoint..."
curl -s -X POST http://localhost:5003/ai/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "List all users from Mumbai"}' | python3 -m json.tool

echo ""
echo "Platform ready!"
echo ""
echo "   API Gateway:  http://localhost:8000"
echo "   AI Service:   http://localhost:5003/docs   (Swagger UI)"
echo "   Ollama API:   http://localhost:11434"
echo "   User Svc:     http://localhost:5001"
echo "   Order Svc:    http://localhost:5002"
