# Official Playwright Python image containing all browser binaries & Linux system dependencies
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Set non-interactive environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    MAX_CONCURRENT=3

# Copy requirements and install
COPY web_app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY web_app /app/web_app
COPY extension /app/extension
COPY README.md /app/README.md

EXPOSE 8000

# Run FastAPI via Uvicorn in production mode
CMD ["uvicorn", "web_app.app:app", "--host", "0.0.0.0", "--port", "8000"]
