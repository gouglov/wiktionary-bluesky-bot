FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY wiktionary_bluesky_bot.py .
COPY scheduler.py .

# Create volume for persistence
VOLUME /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the scheduler
CMD ["python", "scheduler.py"]
