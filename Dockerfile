FROM python:3.10-slim

WORKDIR /app

# Install dependencies first (better layer caching — only reinstalls if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY src/ ./src/
COPY report_cli.py .

# Logs directory for SQLite db (mounted as a volume at runtime, not baked into the image)
RUN mkdir -p logs

# Default command: run the orchestrator's demo query
CMD ["python", "-m", "src.orchestrator"]