FROM python:3.9-slim

# Install cron and other necessary packages
RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the main script and other necessary files
COPY main.py /app/main.py
# Copy the crontab file
COPY crontab /etc/cron.d/scraper-crontab

# Set proper permissions for crontab
RUN chmod 0644 /etc/cron.d/scraper-crontab

# Apply the crontab
RUN crontab /etc/cron.d/scraper-crontab

# Create log directory
RUN mkdir -p /var/log

# Create the log file to be able to run tail
RUN touch /var/log/scraper.log

# Start cron in foreground
CMD ["cron", "-f"]
