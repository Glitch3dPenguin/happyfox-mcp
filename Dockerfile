FROM python:3.12-slim

WORKDIR /app

# Install deps first (better layer caching — only re-runs if requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server
COPY happyfox_mcp.py .

# Streamable HTTP is the default transport for container deployments
ENV MCP_TRANSPORT=streamable-http
ENV PORT=8000

EXPOSE 8000

CMD ["python", "happyfox_mcp.py"]
