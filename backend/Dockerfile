FROM python:3.10-slim

WORKDIR /app

# Cài các dependencies hệ thống để hỗ trợ cài gunicorn và các lib khác
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cài dependencies Python
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy code vào container
COPY . .

# Expose cổng
EXPOSE 10000

# Chạy app bằng gunicorn với UvicornWorker
CMD ["gunicorn", "server:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:10000", "--timeout", "300", "--forwarded-allow-ips", "*"]
