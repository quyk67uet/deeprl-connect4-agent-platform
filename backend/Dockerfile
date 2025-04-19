FROM python:3.10-slim

WORKDIR /app

# Cài các dependencies hệ thống cơ bản
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Tối ưu môi trường
ENV PYTHONUNBUFFERED=1
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1

# Copy & cài Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy toàn bộ source code
COPY . .

# Sử dụng biến môi trường PORT (do Render cung cấp)
EXPOSE 8000

# Entrypoint khởi chạy app với port lấy từ biến môi trường
CMD ["sh", "-c", "gunicorn server:app --workers=1 --worker-class=uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120 --forwarded-allow-ips '*'"]
