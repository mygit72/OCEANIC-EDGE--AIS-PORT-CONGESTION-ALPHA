FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose port
EXPOSE 8000

# Run the API (serves dashboard at / and API at /api/*)
CMD ["uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8000"]
