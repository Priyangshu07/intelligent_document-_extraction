FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PyMuPDF and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libpq-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Set Python path
ENV PYTHONPATH=/app/backend

# Expose port
EXPOSE 8000

# Run the application
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
