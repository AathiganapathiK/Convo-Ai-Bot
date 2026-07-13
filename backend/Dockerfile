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

# Create virtual environment to isolate dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# STAGE 2: Runtime Runner
# ==========================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime dependencies: curl (for healthcheck), gnupg2 (for keys), and unixodbc
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    apt-transport-https \
    ca-certificates \
    unixodbc \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Drivers 17 and 18 for SQL Server
# Note: Adding both driver versions ensures full compatibility regardless of connection configurations
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql17 \
    msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Copy python virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root system user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# Copy application source code
COPY --chown=appuser:appgroup . /app

# Ensure entrypoint script is executable
RUN chmod +x /app/startup.sh

# Use the non-root user
USER appuser

# Expose backend service port
EXPOSE 8000

# Perform health check against the home route
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

# Launch using startup script
ENTRYPOINT ["/app/startup.sh"]
