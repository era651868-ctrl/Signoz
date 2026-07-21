import time
import random
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# 1. Setup OpenTelemetry pipeline pointing to local SigNoz ports
resource = Resource.create(attributes={"service.name": "health-alert-bot"})
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("bot-tracer")

def check_server_vitals():
    # Simulates checking resources
    cpu_usage = random.randint(10, 95)
    memory_usage = random.randint(30, 90)
    return cpu_usage, memory_usage

def main():
    print("🚀 Health Alert Bot started running...")
    while True:
        # Open an explicit tracking span for each execution cycle
        with tracer.start_as_current_span("monitor_cycle") as span:
            cpu, mem = check_server_vitals()
            
            span.set_attribute("system.cpu.usage", cpu)
            span.set_attribute("system.memory.usage", mem)
            
            if cpu > 80:
                with tracer.start_as_current_span("trigger_alert") as alert_span:
                    alert_span.set_attribute("alert.level", "CRITICAL")
                    print(f"⚠️ ALERT! High CPU usage detected: {cpu}%")
            else:
                print(f"✅ System stable. CPU: {cpu}%, Mem: {mem}%")
                
        time.sleep(5) # Run every 5 seconds

if __name__ == "__main__":
    main()
                  
