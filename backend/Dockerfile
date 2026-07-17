# ==========================================
# STAGE 1: Build Dependencies
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compiler tools and unixODBC development headers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    unixodbc-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements from backend folder
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# STAGE 2: Runtime
# ==========================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Allow imports like:
# import core.config
ENV PYTHONPATH=/app

# Install runtime packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    apt-transport-https \
    ca-certificates \
    unixodbc \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft SQL Server ODBC Drivers
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | \
    gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
    > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql17 \
        msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

# Copy Python virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# ==========================================
# Copy Backend Application
# ==========================================

# Copy backend source code
COPY --chown=appuser:appgroup backend/ /app/

# Copy centralized environment files
COPY --chown=appuser:appgroup .local.env /app/
COPY --chown=appuser:appgroup .docker.env /app/
COPY --chown=appuser:appgroup .server.env /app/

# Ensure startup script is executable
RUN chmod +x /app/startup.sh

# Switch to non-root user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Start application
ENTRYPOINT ["/app/startup.sh"]