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
COPY log_file_server.py /app/log_file_server.py
# Copy the crontab file
COPY crontab /etc/cron.d/scraper-crontab

# Set proper permissions for crontab
RUN chmod 0644 /etc/cron.d/scraper-crontab

# Apply the crontab
RUN crontab /etc/cron.d/scraper-crontab

# Create log directory and logs subdirectory for the log server
RUN mkdir -p /var/log
RUN mkdir -p /app/logs

# Create the log files
RUN touch /var/log/scraper.log
RUN touch /app/logs/scraper.log

# Create articles directory
RUN mkdir -p /app/articles

# Create startup script to run both services
RUN echo '#!/bin/bash\n\
\n\
# Function to sync logs\n\
sync_logs() {\n\
    while true; do\n\
        if [ -f /var/log/scraper.log ]; then\n\
            cp /var/log/scraper.log /app/logs/scraper.log 2>/dev/null || true\n\
        fi\n\
        sleep 5\n\
    done\n\
}\n\
\n\
# Run initial scrape\n\
echo "Running initial scrape..."\n\
cd /app && python main.py >> /var/log/scraper.log 2>&1\n\
cp /var/log/scraper.log /app/logs/scraper.log 2>/dev/null || true\n\
echo "Initial scrape completed at $(date)" | tee -a /var/log/scraper.log /app/logs/scraper.log\n\
\n\
# Start cron\n\
echo "Starting cron..."\n\
cron\n\
\n\
# Start log sync in background\n\
sync_logs &\n\
\n\
# Start log file server in background\n\
echo "Starting log file server on port 8080..."\n\
python log_file_server.py &\n\
\n\
# Follow scraper logs\n\
echo "Following scraper logs..."\n\
tail -f /var/log/scraper.log' > /app/start.sh && chmod +x /app/start.sh

# Use the startup script
CMD ["/app/start.sh"]
