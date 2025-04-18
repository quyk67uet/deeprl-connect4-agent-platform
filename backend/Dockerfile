FROM python:3.10-slim

WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Expose the port the app runs on
EXPOSE 10000

# Command to run the application
CMD ["gunicorn", "server:app", "--bind", "0.0.0.0:10000", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120"]