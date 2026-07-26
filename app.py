import json
import os
import random
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

try:
    import psutil
except ImportError:
    psutil = None

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


SERVICE_NAME = os.getenv("SERVICE_NAME", "health-alert-bot")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "5"))
CPU_ALERT_THRESHOLD = int(os.getenv("CPU_ALERT_THRESHOLD", "80"))
MEMORY_ALERT_THRESHOLD = int(os.getenv("MEMORY_ALERT_THRESHOLD", "85"))
DISK_ALERT_THRESHOLD = int(os.getenv("DISK_ALERT_THRESHOLD", "85"))
INCIDENTS_FILE = os.getenv("INCIDENTS_FILE", "incidents.jsonl")
METRICS_HISTORY_LIMIT = int(os.getenv("METRICS_HISTORY_LIMIT", "50"))
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))

metrics_history = []


def is_otlp_endpoint_reachable(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4317
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def setup_tracing():
    resource = Resource.create(attributes={"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if is_otlp_endpoint_reachable(OTLP_ENDPOINT):
        exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        print(f"📡 Tracing enabled. Sending spans to {OTLP_ENDPOINT}")
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        print(f"⚠️ OTLP endpoint {OTLP_ENDPOINT} is not reachable. Falling back to console spans.")

    trace.set_tracer_provider(provider)
    return trace.get_tracer("bot-tracer")


tracer = setup_tracing()


def collect_metrics():
    if psutil is not None:
        cpu_usage = round(psutil.cpu_percent(interval=None), 1)
        memory_usage = round(psutil.virtual_memory().percent, 1)
        disk_usage = round(psutil.disk_usage("/").percent, 1)
        return {
            "cpu_percent": cpu_usage,
            "memory_percent": memory_usage,
            "disk_percent": disk_usage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "cpu_percent": random.randint(10, 95),
        "memory_percent": random.randint(30, 90),
        "disk_percent": random.randint(20, 90),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def evaluate_health(metrics):
    reasons = []
    severity = "NORMAL"

    if metrics["cpu_percent"] > CPU_ALERT_THRESHOLD:
        severity = "CRITICAL"
        reasons.append("high_cpu")
    if metrics["memory_percent"] > MEMORY_ALERT_THRESHOLD:
        severity = "WARNING" if severity == "NORMAL" else severity
        reasons.append("high_memory")
    if metrics["disk_percent"] > DISK_ALERT_THRESHOLD:
        severity = "WARNING" if severity == "NORMAL" else severity
        reasons.append("high_disk")

    return severity, reasons


def record_incident(metrics, severity, reasons, incidents_file=None):
    incident = {
        "timestamp": metrics["timestamp"],
        "cpu_percent": metrics["cpu_percent"],
        "memory_percent": metrics["memory_percent"],
        "disk_percent": metrics["disk_percent"],
        "severity": severity,
        "reasons": reasons,
    }
    metrics_history.append(incident)
    if len(metrics_history) > METRICS_HISTORY_LIMIT:
        metrics_history[:] = metrics_history[-METRICS_HISTORY_LIMIT:]

    target_file = incidents_file or INCIDENTS_FILE
    with open(target_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(incident) + "\n")
    return incident


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Health Alert Bot Dashboard</title>
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --text: #f8fafc;
            --accent: #38bdf8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 15px; }
        .badge { padding: 4px 12px; border-radius: 9999px; font-weight: bold; font-size: 0.85rem; }
        .bg-normal { background: rgba(34, 197, 94, 0.2); color: var(--success); border: 1px solid var(--success); }
        .bg-warning { background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid var(--warning); }
        .bg-critical { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 20px; }
        .card { background: var(--card); border-radius: 12px; padding: 20px; border: 1px solid #334155; }
        .card h3 { margin: 0 0 10px 0; font-size: 1rem; color: #94a3b8; }
        .value { font-size: 2rem; font-weight: bold; }
        
        .progress-bar { background: #334155; height: 8px; border-radius: 4px; margin-top: 10px; overflow: hidden; }
        .progress-fill { height: 100%; width: 0%; transition: width 0.3s ease; }
        
        .logs { margin-top: 30px; background: var(--card); border-radius: 12px; padding: 20px; border: 1px solid #334155; }
        .log-entry { font-family: monospace; font-size: 0.85rem; padding: 8px 0; border-bottom: 1px solid #334155; }
        .log-entry:last-child { border-bottom: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🤖 Health Alert Bot</h2>
            <span id="status-badge" class="badge bg-normal">SYSTEM ONLINE</span>
        </div>

        <div class="grid">
            <div class="card">
                <h3>CPU Usage</h3>
                <div class="value" id="cpu-val">--%</div>
                <div class="progress-bar"><div id="cpu-bar" class="progress-fill" style="background: var(--accent);"></div></div>
            </div>
            <div class="card">
                <h3>Memory Usage</h3>
                <div class="value" id="mem-val">--%</div>
                <div class="progress-bar"><div id="mem-bar" class="progress-fill" style="background: var(--accent);"></div></div>
            </div>
            <div class="card">
                <h3>Disk Usage</h3>
                <div class="value" id="disk-val">--%</div>
                <div class="progress-bar"><div id="disk-bar" class="progress-fill" style="background: var(--accent);"></div></div>
            </div>
        </div>

        <div class="logs">
            <h3>Recent Telemetry History</h3>
            <div id="log-list">Loading telemetry...</div>
        </div>
    </div>

    <script>
        async function updateDashboard() {
            try {
                const res = await fetch('/metrics');
                const data = await res.json();
                if (!data.latest) return;

                const { cpu_percent, memory_percent, disk_percent, severity } = data.latest;
                
                document.getElementById('cpu-val').innerText = cpu_percent + '%';
                document.getElementById('mem-val').innerText = memory_percent + '%';
                document.getElementById('disk-val').innerText = disk_percent + '%';

                document.getElementById('cpu-bar').style.width = cpu_percent + '%';
                document.getElementById('mem-bar').style.width = memory_percent + '%';
                document.getElementById('disk-bar').style.width = disk_percent + '%';

                const badge = document.getElementById('status-badge');
                badge.innerText = severity || 'NORMAL';
                badge.className = 'badge ' + (severity === 'CRITICAL' ? 'bg-critical' : severity === 'WARNING' ? 'bg-warning' : 'bg-normal');

                const logList = document.getElementById('log-list');
                logList.innerHTML = data.history.reverse().map(item => `
                    <div class="log-entry">
                        [${item.timestamp}] Severity: <strong>${item.severity}</strong> | CPU: ${item.cpu_percent}% | MEM: ${item.memory_percent}% | DISK: ${item.disk_percent}%
                    </div>
                `).join('');
            } catch (e) {
                console.error("Failed to fetch metrics", e);
            }
        }

        setInterval(updateDashboard, 3000);
        updateDashboard();
    </script>
</body>
</html>
"""


class HealthRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            self._send_html(200, HTML_DASHBOARD)
        elif self.path == "/health":
            self._send_json(200, {"status": "ok", "service": SERVICE_NAME})
        elif self.path == "/metrics":
            self._send_json(200, {"latest": metrics_history[-1] if metrics_history else None, "history": metrics_history[-10:]})
        elif self.path == "/incidents":
            self._send_json(200, {"incidents": metrics_history[-10:]})
        else:
            self._send_json(404, {"error": "not_found"})

    def log_message(self, format, *args):
        return

    def _send_html(self, status_code, html_content):
        body = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_http_server():
    server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), HealthRequestHandler)
    print(f"🌐 Metrics dashboard available at http://{HTTP_HOST}:{HTTP_PORT}")
    server.serve_forever()


def build_status_message(metrics, severity):
    if severity == "CRITICAL":
        return (
            f"⚠️ ALERT! Severe issue detected: CPU {metrics['cpu_percent']}%, "
            f"Mem {metrics['memory_percent']}%, Disk {metrics['disk_percent']}%"
        )
    if severity == "WARNING":
        return f"⚠️ Warning. CPU: {metrics['cpu_percent']}%, Mem: {metrics['memory_percent']}%, Disk: {metrics['disk_percent']}%"
    return f"✅ System stable. CPU: {metrics['cpu_percent']}%, Mem: {metrics['memory_percent']}%, Disk: {metrics['disk_percent']}%"


def main():
    threading.Thread(target=start_http_server, daemon=True).start()
    print("🚀 Health Alert Bot started running...")
    print(f"📊 Monitoring every {CHECK_INTERVAL_SECONDS}s | CPU threshold: {CPU_ALERT_THRESHOLD}% | Memory threshold: {MEMORY_ALERT_THRESHOLD}%")

    while True:
        metrics = collect_metrics()
        severity, reasons = evaluate_health(metrics)

        with tracer.start_as_current_span("monitor_cycle") as span:
            span.set_attribute("system.cpu.usage", metrics["cpu_percent"])
            span.set_attribute("system.memory.usage", metrics["memory_percent"])
            span.set_attribute("system.disk.usage", metrics["disk_percent"])
            span.set_attribute("alert.threshold.cpu", CPU_ALERT_THRESHOLD)
            span.set_attribute("alert.threshold.memory", MEMORY_ALERT_THRESHOLD)
            span.set_attribute("health.severity", severity)

            if severity == "CRITICAL":
                with tracer.start_as_current_span("trigger_alert") as alert_span:
                    alert_span.set_attribute("alert.level", "CRITICAL")
                    alert_span.set_attribute("alert.reason", ",".join(reasons))
                    alert_span.add_event("cpu_threshold_exceeded", {"cpu_percent": metrics["cpu_percent"]})
            print(build_status_message(metrics, severity))

        record_incident(metrics, severity, reasons)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
    
