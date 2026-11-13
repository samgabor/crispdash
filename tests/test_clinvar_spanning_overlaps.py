"""Region-query regression tests using mocked E-utilities responses."""
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from services.clinvar import annotate_clinvar_region, search_clinvar_region


def search_response(ids, total):
    response = Mock()
    response.json.return_value = {"esearchresult": {"count": str(total), "idlist": ids}}
    return response


def record(start, end, chrom="6", assembly="GRCh38", classification="Uncertain significance"):
    return {
        "title": "Candidate variant",
        "germline_classification": {
            "description": classification, "review_status": "criteria provided, single submitter",
            "trait_set": [{"trait_name": "Example condition"}],
        },
        "variation_set": [{"variation_loc": [{
            "assembly_name": assembly, "chr": chrom, "start": start, "stop": end,
        }]}],
    }


class SpanningOverlapTests(unittest.TestCase):
    def test_query_preserves_narrow_matches_and_adds_spanning_candidates(self):
        with patch("services.clinvar.ncbi_get", return_value=search_response([], 0)) as get:
            result = search_clinvar_region("chr6", 20203311, 20203333)
        self.assertEqual(get.call_args.args[1]["term"],
                         "6[chr] AND (20203311:20203333[chrpos38] OR "
                         "(1:20203333[chrpos38] AND 20203311:999999999[chrpos38]))")
        self.assertNotIn("clinsig", result["search_term"])

    def test_candidates_still_require_actual_grch38_overlap(self):
        # Broad searches can match positions from different placements. Only
        # one valid interval on the correct assembly/chromosome may qualify.
        records = [
            record(12020008, 22846454, classification="Pathogenic"),  # spanning CNV
            record(20203320, 20203320),  # small VUS: region search accepts it
            record(20203300, 20203311),  # inclusive left boundary
            record(20203333, 20203400),  # inclusive right boundary
            record(20203300, 20203310),  # wholly before
            record(20203334, 20203400),  # wholly after
            record(12020008, 22846454, chrom="7"),
            record(12020008, 22846454, assembly="GRCh37"),
        ]
        ids = [str(i) for i in range(len(records))]
        with (
            patch("services.clinvar.ncbi_get", return_value=search_response(ids, len(ids))),
            patch("services.clinvar.get_clinvar_variant_details", side_effect=records),
        ):
            result = annotate_clinvar_region("chr6", 20203311, 20203333)
        self.assertEqual([v["clinvar_id"] for v in result["verified_variants"]], ids[:4])
        self.assertEqual(result["verified_variants"][1]["clinical_significance"], "Uncertain significance")
        self.assertEqual(result["verified_variants"][0]["conditions"], "Example condition")
        self.assertEqual(result["records_retrieved"], 8)
        self.assertEqual(result["records_examined"], 8)

    def test_empty_region_search_reports_zero_examined(self):
        with patch("services.clinvar.ncbi_get", return_value=search_response([], 0)):
            result = annotate_clinvar_region("6", 20, 42)
        self.assertEqual(result["records_examined"], 0)
        self.assertEqual(result["verified_variants"], [])
        self.assertFalse(result["truncated"])

    def test_default_limit_is_1000_with_100_record_pages(self):
        responses = [search_response([str(n) for n in range(i, i+100)], 2500)
                     for i in range(0, 1000, 100)]
        with patch("services.clinvar.ncbi_get", side_effect=responses) as get:
            result = search_clinvar_region("6", 20, 42)
        self.assertEqual(result["total_count"], 2500)
        self.assertEqual(result["records_retrieved"], 1000)
        self.assertTrue(result["truncated"])
        self.assertEqual([c.args[1]["retstart"] for c in get.call_args_list], list(range(0, 1000, 100)))
        self.assertTrue(all(c.args[1]["retmax"] == 100 for c in get.call_args_list))

    def test_duplicate_ids_do_not_repeat_summary_lookups_or_stall_pagination(self):
        ids = [str(i) for i in range(100)]
        responses = [search_response(ids, 102), search_response(["99", "100"], 102)]
        with (
            patch("services.clinvar.ncbi_get", side_effect=responses) as get,
            patch("services.clinvar.get_clinvar_variant_details", return_value=record(20, 20)) as details,
        ):
            result = annotate_clinvar_region("6", 20, 42)
        self.assertEqual([c.args[1]["retstart"] for c in get.call_args_list], [0, 100])
        self.assertEqual(details.call_count, 101)
        self.assertEqual(result["records_retrieved"], 101)
        self.assertEqual(len(result["verified_variants"]), 101)
        self.assertTrue(result["truncated"])

    def test_retrieval_limit_and_empty_page_stop_pagination(self):
        with patch("services.clinvar.ncbi_get", side_effect=[
            search_response([str(i) for i in range(100)], 250),
            search_response([str(i) for i in range(100, 150)], 250),
        ]) as get:
            result = search_clinvar_region("6", 20, 42, max_records=150)
        self.assertEqual([c.args[1]["retmax"] for c in get.call_args_list], [100, 50])
        self.assertEqual(result["records_retrieved"], 150)
        self.assertTrue(result["truncated"])
        with patch("services.clinvar.ncbi_get", return_value=search_response([], 250)) as get:
            result = search_clinvar_region("6", 20, 42)
        self.assertEqual(get.call_count, 1)
        self.assertTrue(result["truncated"])

    def test_invalid_inputs_do_not_make_requests(self):
        for start, end, limit in [(0, 10, 1000), (20, 10, 1000), (1, 10, 0)]:
            with self.subTest(start=start, end=end, limit=limit):
                with patch("services.clinvar.ncbi_get") as get:
                    with self.assertRaises(ValueError):
                        search_clinvar_region("6", start, end, max_records=limit)
                    get.assert_not_called()


def region_counts_page():
    import pandas as pd
    import streamlit as st
    from ui.analysis_results import render_annotation_results
    tabs = st.tabs(["Genes", "Exons", "Site ClinVar", "Gene ClinVar", "Summary"])
    slots = {key: tab.empty() for key, tab in zip(
        ["genes", "exons", "direct", "gene", "summary"], tabs)}
    snapshot = {
        "values": {("genes",): [], ("exons",): [], ("clinvar",): {
            "search_count": 2500, "records_retrieved": 1000, "records_examined": 1000,
            "verified_variants": [], "truncated": True}},
        "errors": {}, "timings": {}, "complete": False, "pending": [],
    }
    render_annotation_results(snapshot, pd.Series(dict(chrom="6", start=20, end=42)),
                              "SITE-006", slots, st.empty())


class RegionCountsUITests(unittest.TestCase):
    def test_search_matches_are_not_mislabeled_as_records_retrieved(self):
        app = AppTest.from_function(region_counts_page).run()
        self.assertFalse(app.exception)
        captions = [c.value for c in app.caption]
        self.assertIn("ClinVar region-search matches: 2500", captions)
        self.assertTrue(any("records retrieved: 1000" in c and "examined: 1000" in c for c in captions))
        self.assertFalse(any("records retrieved: 2500" in c for c in captions))
        self.assertTrue(any("retrieval limit" in w.value for w in app.warning))


if __name__ == "__main__":
    unittest.main()
