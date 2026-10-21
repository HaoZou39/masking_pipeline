"""Offline tests for the per-stage end-to-end timing report."""
import json
import os
import tempfile
import time
import unittest

from run import _ACTIVE_BENCHMARK, _stage, benchmarked_pipeline, run_pipeline


class BenchmarkTests(unittest.TestCase):
    def test_successful_stage_writes_timing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            @benchmarked_pipeline
            def sample(*, fresh=False):
                _ACTIVE_BENCHMARK.get()["site_dir"] = tmp
                _stage("download", lambda: "ok")
                _stage("segment", lambda: "ok")
                return {"site_id": "sample"}

            sample(fresh=True)
            report = json.loads(open(os.path.join(tmp, "timing_report.json"), encoding="utf-8").read())
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["mode"], "cold")
            self.assertEqual([x["stage"] for x in report["stages"]], ["download", "segment"])
            self.assertGreaterEqual(report["total_wall_seconds"], 0.0)

    def test_failed_stage_persists_partial_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            @benchmarked_pipeline
            def sample(*, fresh=False):
                _ACTIVE_BENCHMARK.get()["site_dir"] = tmp
                def error():
                    raise RuntimeError("download refused")
                _stage("download", error)
                return {}

            with self.assertRaisesRegex(RuntimeError, "download refused"):
                sample(fresh=True)
            report = json.loads(open(os.path.join(tmp, "timing_report.json"), encoding="utf-8").read())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["stages"][0]["status"], "failed")

    def test_fresh_does_not_allow_partial_or_resume(self):
        with self.assertRaisesRegex(ValueError, "requires --step all"):
            run_pipeline(27.501662, 120.194639, fresh=True, step="osm")
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            run_pipeline(27.501662, 120.194639, fresh=True, resume=True)


if __name__ == "__main__":
    unittest.main()
