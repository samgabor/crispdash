"""Offline coverage of REST timing, retries, isolation, and UI display."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import Mock, patch

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from services.ensembl import ensembl_get
from services.timing import capture_request_timings, timed_get, timed_lookup


class RequestTimingTests(unittest.TestCase):
    def test_debug_visibility_and_repeated_analysis_navigation(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.addCleanup(st.cache_data.clear)
        self.addCleanup(st.cache_resource.clear)
        request = dict(provider="Ensembl", endpoint="/test", query="", status="HTTP 200", elapsed_seconds=0.1)
        result = {
            "values": {("genes",): [], ("exons",): [], ("clinvar",): {
                "verified_variants": [], "search_count": 0, "truncated": False}},
            "errors": {},
            "timings": {key: {"elapsed_seconds": 0.2, "requests": [request]}
                        for key in [("genes",), ("exons",), ("clinvar",)]},
            "elapsed_seconds": 0.3, "retrieved_at": "2026-11-10T12:00:00+00:00",
        }
        with (
            patch("config.DEBUG", False),
            patch("services.annotations.collect_annotations", return_value=result) as lookup,
        ):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.session_state["main_tab"], "Site Analysis")
            self.assertFalse(any(e.label == "HTTP response times" for e in app.expander))
            self.assertTrue(any("Lookup time:" in c.value for c in app.caption))
            self.assertFalse(any("Response time (s)" in f.value.columns for f in app.dataframe))

            # Existing sessions using the old capitalization are normalized.
            app.session_state["main_tab"] = "Explore sites"
            app.run()
            self.assertEqual(app.session_state["main_tab"], "Explore Sites")
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.session_state["main_tab"], "Site Analysis")
            self.assertEqual(lookup.call_count, 1)

            # Debug details can be shown for the same cached results.
            with patch("config.DEBUG", True):
                app.run()
                self.assertFalse(app.exception, app.exception)
                self.assertEqual(sum(e.label == "HTTP response times" for e in app.expander), 3)
                self.assertEqual(lookup.call_count, 1)

    def test_success_measures_response_and_omits_credentials(self):
        records = []
        response = Mock(status_code=200)
        with (
            patch("services.timing.requests.get", return_value=response),
            patch("services.timing.time.perf_counter", side_effect=[10.0, 10.75]),
            capture_request_timings(records),
        ):
            self.assertIs(timed_get("NCBI", "https://example.org/esearch.fcgi?api_key=secret",
                                   params={"db": "gene", "term": "TEST[sym]", "api_key": "secret", "email": "private@example.org"}), response)
        self.assertEqual(records[0]["elapsed_seconds"], 0.75)
        self.assertEqual(records[0]["status"], "HTTP 200")
        self.assertEqual(records[0]["endpoint"], "/esearch.fcgi")
        self.assertNotIn("secret", str(records))
        self.assertNotIn("private@example.org", str(records))

    def test_timeout_keeps_attempt_timing_and_lookup_error(self):
        with patch("services.timing.requests.get", side_effect=requests.Timeout("Timed out")):
            result = timed_lookup(timed_get, "Ensembl", "https://example.org/lookup/id/TEST")
        self.assertEqual(result["error"], "Timed out")
        self.assertEqual(result["requests"][0]["status"], "Timeout")
        self.assertGreaterEqual(result["elapsed_seconds"], result["requests"][0]["elapsed_seconds"])

    def test_retries_record_separate_response_times(self):
        records = []
        with (
            patch("services.timing.requests.get", side_effect=[Mock(status_code=500), Mock(status_code=200)]),
            patch("services.ensembl._request_limiter.wait"),
            patch("services.ensembl.time.sleep"),
            patch("services.timing.time.perf_counter", side_effect=[1.0, 1.2, 2.0, 2.35]),
            capture_request_timings(records),
        ):
            ensembl_get("https://example.org/lookup/id/TEST")
        self.assertEqual([r["status"] for r in records], ["HTTP 500", "HTTP 200"])
        self.assertAlmostEqual(records[0]["elapsed_seconds"], 0.2)
        self.assertAlmostEqual(records[1]["elapsed_seconds"], 0.35)

    def test_parallel_lookups_keep_their_own_requests(self):
        barrier = Barrier(2, timeout=3)

        def lookup(identifier):
            barrier.wait()
            return timed_get("Ensembl", f"https://example.org/lookup/id/{identifier}")

        with patch("services.timing.requests.get", return_value=Mock(status_code=200)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                a, b = list(pool.map(lambda name: timed_lookup(lookup, name), ["A", "B"]))
        self.assertEqual([r["endpoint"] for r in a["requests"]], ["/lookup/id/A"])
        self.assertEqual([r["endpoint"] for r in b["requests"]], ["/lookup/id/B"])

    def test_app_displays_each_rest_attempt_and_preserves_cached_timings(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.addCleanup(st.cache_data.clear)
        self.addCleanup(st.cache_resource.clear)

        def get(url, params=None, **kwargs):
            data = ({"esearchresult": {"count": "0", "idlist": []}}
                    if "esearch.fcgi" in url else [])
            return Mock(status_code=200, json=Mock(return_value=data))

        with patch("config.DEBUG", True), patch("services.timing.requests.get", side_effect=get) as query:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            tables = [frame.value for frame in app.dataframe
                      if "Response time (s)" in frame.value.columns]
            self.assertEqual(sum(len(frame) for frame in tables), 3)
            self.assertEqual(query.call_count, 3)
            caption = next(c.value for c in app.caption if "Original fetch:" in c.value)
            app.run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(query.call_count, 3)
            self.assertTrue(any(c.value == caption for c in app.caption))


if __name__ == "__main__":
    unittest.main()
