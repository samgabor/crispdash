"""Pending annotation data must not be presented as negative evidence."""
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services.annotation_cache import AnnotationCache


class ProgressiveDisplayTests(unittest.TestCase):
    def test_ready_tabs_render_while_other_tabs_show_loading(self):
        def page():
            import pandas as pd
            import streamlit as st
            from ui.analysis_results import render_annotation_results

            gene = dict(gene_id="ENSG_TEST", gene_name="TEST", chromosome="1",
                        start=1, end=100, strand=1, biotype="protein_coding",
                        description="Available gene description")
            snapshot = {
                "values": {("genes",): [gene], ("gene_information", "ENSG_TEST"): gene,
                           ("exons",): []},
                "errors": {}, "timings": {}, "complete": False,
                "pending": [("clinvar",), ("ncbi_summary", "TEST"), ("gene_clinvar", "ENSG_TEST")],
            }
            status = st.empty()
            tabs = st.tabs(["Genes", "Exons", "Site ClinVar", "Gene ClinVar", "Summary"])
            slots = {key: tab.empty() for key, tab in zip(
                ["genes", "exons", "direct", "gene", "summary"], tabs)}
            render_annotation_results(snapshot, pd.Series(dict(chrom="1", start=20, end=42)),
                                      "SITE-001", slots, status)

        app = AppTest.from_function(page).run()
        self.assertFalse(app.exception, app.exception)
        messages = [info.value for info in app.info]
        self.assertTrue(any("No overlapping exons" in m for m in messages))
        self.assertTrue(any("Loading ClinVar site overlaps" in m for m in messages))
        self.assertTrue(any("Loading biological function" in m for m in messages))
        self.assertTrue(any("Loading ClinVar context" in m for m in messages))
        self.assertTrue(any("Evidence summary will be available" in m for m in messages))
        self.assertFalse(any("No matching NCBI" in m or "No verified ClinVar" in m for m in messages))
        self.assertFalse(any("Evidence Category" in frame.value.columns for frame in app.dataframe))

    def test_cache_expires_and_does_not_store_partial_failures(self):
        cache = AnnotationCache(ttl=1)
        complete = {"values": {("genes",): []}, "errors": {}}
        with patch("services.annotation_cache.monotonic", side_effect=[0, 0.5, 2]):
            cache.put("site", complete)
            cached = cache.get("site")
            self.assertEqual(cached, complete)
            cached["values"].clear()
            self.assertEqual(complete["values"], {("genes",): []})
            self.assertIsNone(cache.get("site"))
        cache.put("failed", {"values": {}, "errors": {("genes",): "Timeout"}})
        self.assertIsNone(cache.get("failed"))


if __name__ == "__main__":
    unittest.main()
