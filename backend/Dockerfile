FROM python:3.10-slim

WORKDIR /app

# Cài đặt các dependencies cần thiết
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Expose application port
EXPOSE 10000

# Run the application with SSL options for WebSocket/HTTPS support
CMD ["gunicorn", "server:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:10000", "--timeout", "300", "--forwarded-allow-ips", "*", "--proxy-headers"]