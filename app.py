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
except ImportError:  # pragma: no cover - optional dependency
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

    # Keep the bot running even if the collector is temporarily unavailable.
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


class HealthRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send_json(200, {"status": "ok", "service": SERVICE_NAME})
        elif self.path == "/metrics":
            self._send_json(200, {"latest": metrics_history[-1] if metrics_history else None, "history": metrics_history[-10:]})
        elif self.path == "/incidents":
            self._send_json(200, {"incidents": metrics_history[-10:]})
        else:
            self._send_json(404, {"error": "not_found"})

    def log_message(self, format, *args):
        return

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


