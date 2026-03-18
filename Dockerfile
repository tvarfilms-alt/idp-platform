FROM python:3.12-slim

WORKDIR /app

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY etl/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY etl/ /app/etl/
COPY compute/ /app/compute/

# Cron schedule (MSK = UTC+3)
# ETL MOEX: Mon-Fri 16:30 UTC (19:30 MSK)
# ETL CBR:  Mon-Fri 17:00 UTC (20:00 MSK)
# ETL FM:   Monday  05:30 UTC (08:30 MSK)
# Compute L2+Bonds: Mon-Fri 18:00 UTC (21:00 MSK)
# Compute L1: 1st of month 07:00 UTC (10:00 MSK)
# Compute L3: Monday 05:00 UTC (08:00 MSK)
# Quality check: Daily 18:30 UTC (21:30 MSK)

COPY scripts/crontab /etc/cron.d/idp-cron
RUN chmod 0644 /etc/cron.d/idp-cron && crontab /etc/cron.d/idp-cron

# Entrypoint: start cron in foreground
CMD ["cron", "-f"]
