"""Classification filters keep broader overlaps available without another lookup."""
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from services.clinvar import filter_clinvar_overlaps, is_pathogenic_classification
from tests.test_search_parameters import APP, empty_snapshot


def mixed_snapshot(*args, **kwargs):
    snapshot = empty_snapshot(*args, **kwargs)
    variants = []
    for index, significance in enumerate([
        "Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic",
        "association", "Uncertain significance", "Conflicting classifications of pathogenicity",
    ]):
        variants.append({
            "clinvar_id": str(index + 1), "variant_name": f"Variant {index + 1}",
            "clinical_significance": significance, "review_status": "reviewed",
            "conditions": "Test condition", "locations": [
                {"chromosome": "1", "start": 1, "end": 100}],
        })
    snapshot["values"][("clinvar",)] = {
        "search_count": 6, "records_retrieved": 6, "records_examined": 6,
        "verified_variants": variants, "truncated": False,
    }
    return snapshot


class ClassificationFilterTests(unittest.TestCase):
    def test_exact_categories_exclude_conflicts_and_other_assertions(self):
        for value in ["Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic",
                      "  PATHOGENIC/LIKELY PATHOGENIC  "]:
            self.assertTrue(is_pathogenic_classification(value), value)
        for value in [None, "", "association", "Uncertain significance", "Benign",
                      "Conflicting classifications of pathogenicity",
                      "Pathogenic/Uncertain significance", "Pathogenic, low penetrance"]:
            self.assertFalse(is_pathogenic_classification(value), value)

    def test_filter_preserves_source_population(self):
        records = [{"clinical_significance": "association"},
                   {"clinical_significance": "Pathogenic"}]
        self.assertEqual(filter_clinvar_overlaps(records), [records[1]])
        self.assertEqual(filter_clinvar_overlaps(records, True), records)
        self.assertEqual(len(records), 2)

    def test_table_summary_and_toggle_use_same_cached_population(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.addCleanup(st.cache_data.clear)
        self.addCleanup(st.cache_resource.clear)
        with patch("services.annotations.collect_annotations", side_effect=mixed_snapshot) as lookup:
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.checkbox(key="clinvar_include_other").value)
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            frames = [frame.value for frame in app.dataframe]
            overlaps = next(frame for frame in frames if "ClinVar ID" in frame.columns)
            self.assertEqual(len(overlaps), 3)
            self.assertTrue(any("records: 6 · Meet the selected classification filter: 3" in
                                caption.value for caption in app.caption))
            summary = next(frame for frame in frames if "Evidence Category" in frame.columns)
            self.assertEqual(summary.loc[summary["Evidence Category"].str.startswith(
                "Direct ClinVar"), "Finding"].iloc[0], "3")
            app.checkbox(key="clinvar_include_other").check().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(lookup.call_count, 1)
            frames = [frame.value for frame in app.dataframe]
            self.assertEqual(len(next(frame for frame in frames if "ClinVar ID" in frame.columns)), 6)
            summary = next(frame for frame in frames if "Evidence Category" in frame.columns)
            self.assertEqual(summary.loc[summary["Evidence Category"].str.startswith(
                "Direct ClinVar"), "Finding"].iloc[0], "6")
            app.selectbox(key="guide").select("CFTR-sgRNA-1").run()
            self.assertTrue(app.checkbox(key="clinvar_include_other").value)


if __name__ == "__main__":
    unittest.main()
