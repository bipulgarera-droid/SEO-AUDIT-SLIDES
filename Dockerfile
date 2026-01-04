FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy requirements first for cache efficiency
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (ensure Chromium is present)
RUN playwright install chromium

# Copy the rest of the application
COPY . .

# Expose the port (Railway sends PORT env var, defaulting to 8080 for local test)
ENV PORT=8080
EXPOSE $PORT

# Command to run the application
# Command to run the application using shell for variable expansion
CMD ["/bin/sh", "-c", "gunicorn api.index:app --bind 0.0.0.0:${PORT:-8080}"]
