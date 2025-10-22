# Use Python 3.13 for best performance
FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies using uv
RUN uv pip install --system -r requirements.txt

# Copy application files
COPY overlay_sync_manager.py .

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Run the application
# Default to daemon mode, but allow override via command line args
ENTRYPOINT ["python", "overlay_sync_manager.py"]
CMD ["config.json"]
