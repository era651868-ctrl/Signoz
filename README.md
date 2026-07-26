# Automated Infrastructure Health & Monitoring Bot

This project is a polished hackathon submission for the SigNoz + WeMakeDevs challenge. It combines OpenTelemetry instrumentation, real-time system monitoring, and a lightweight observability dashboard to show how infrastructure health can be made visible and actionable.

## Why this is a strong hackathon project
This project is built for Track 03: Build Your Own. It demonstrates:
- real-world SRE-style monitoring
- OpenTelemetry-native instrumentation
- anomaly detection for infrastructure health
- a clear observability story for judges and demo audiences

## What it does
- Monitors CPU, memory, and disk usage in real time
- Detects critical and warning-level anomalies
- Emits OpenTelemetry traces and events
- Logs incidents to a JSONL file
- Exposes a simple HTTP dashboard at port 8000 for live metrics

## Why judges will like it
This is not just a script that prints numbers. It shows:
- a practical idea with visible impact
- a strong connection to SigNoz and observability
- a complete developer experience with monitoring, alerts, and a simple dashboard

## Run locally
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the bot:
   ```bash
   python app.py
   ```
3. Open the dashboard:
   - http://127.0.0.1:8000/health
   - http://127.0.0.1:8000/metrics
### Recommended Python version: 3.10+
```bash
pip install -r requirements.txt
python app.py
```


## Optional environment variables
```bash
OTLP_ENDPOINT=http://localhost:4317
CPU_ALERT_THRESHOLD=80
MEMORY_ALERT_THRESHOLD=85
DISK_ALERT_THRESHOLD=85
CHECK_INTERVAL_SECONDS=5
HTTP_PORT=8000
```

## Demo pitch
Show how the bot turns a CPU spike into a visible alert, generates telemetry traces, and exposes the signal through a live metrics endpoint. That makes the project feel closer to a production-ready SRE workflow than a basic demo script.

## Project summary
An automated SRE health-monitoring agent that collects infrastructure signals, detects anomalies, and exports OpenTelemetry traces into a self-hosted SigNoz deployment to provide immediate visibility into system spikes and critical threshold alerts.
