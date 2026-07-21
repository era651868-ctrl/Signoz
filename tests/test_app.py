import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app


class HealthBotTests(unittest.TestCase):
    def test_evaluate_health_marks_critical_on_high_cpu(self):
        metrics = {"cpu_percent": 95, "memory_percent": 60, "disk_percent": 50}
        severity, reasons = app.evaluate_health(metrics)
        self.assertEqual(severity, "CRITICAL")
        self.assertIn("high_cpu", reasons)

    def test_evaluate_health_marks_warning_on_memory_only(self):
        metrics = {"cpu_percent": 40, "memory_percent": 90, "disk_percent": 50}
        severity, reasons = app.evaluate_health(metrics)
        self.assertEqual(severity, "WARNING")
        self.assertIn("high_memory", reasons)

    def test_record_incident_writes_jsonl(self):
        metrics = {"cpu_percent": 88, "memory_percent": 70, "disk_percent": 60, "timestamp": "2026-01-01T00:00:00Z"}
        with tempfile.NamedTemporaryFile("w+", delete=False) as handle:
            temp_path = handle.name
        try:
            incident = app.record_incident(metrics, "WARNING", ["high_cpu"], incidents_file=temp_path)
            self.assertEqual(incident["severity"], "WARNING")
            with open(temp_path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
            self.assertIn("high_cpu", content)
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
