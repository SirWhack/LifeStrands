# Multi-stage build for smaller, more secure images
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash npcservice

# Copy installed packages from builder
COPY --from=builder /root/.local /home/npcservice/.local

# Set working directory and copy application
WORKDIR /app
COPY . .

# Create logs directory and set ownership
RUN mkdir -p /app/logs && chown -R npcservice:npcservice /app

# Switch to non-root user
USER npcservice

# Add user's local bin to PATH
ENV PATH=/home/npcservice/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8003

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8003/health', timeout=5)"

# Run the application
CMD ["python", "main.py"]