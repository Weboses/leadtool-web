# Lead-Tool Web App
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App files
COPY . .

# Create directories
RUN mkdir -p /app/data /app/backups /app/uploads

# Railway stellt PORT bereit - nutze Shell-Form für Variable
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 app:app
