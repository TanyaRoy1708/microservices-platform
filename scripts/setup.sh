#!/bin/bash
# scripts/setup.sh One-command platform setup (Simplified)
set -euo pipefail

echo "Setting up microservices and AI platform..."

# Create .env if missing OR if it exists but is empty
if [ ! -f .env ] || [ ! -s .env ]; then
    cp .env.example .env
    echo "Created .env from template"
fi
echo "Reminder: Edit .env with real passwords before production!"

# Build and start all services
echo "Building and starting all services..."
docker compose up --build -d

# Pull AI model
echo "Pulling AI model (this takes 2-3 mins on first run)..."
docker compose run --rm ollama-model-pull

echo ""
echo "Platform ready!"
echo ""
echo "   API Gateway:  http://localhost:8000"
echo "   AI Service:   http://localhost:5003/docs   (Swagger UI)"
echo "   User Svc:     http://localhost:5001"
echo "   Order Svc:    http://localhost:5002"
