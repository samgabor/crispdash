"""Search settings persist, apply on Analyze, and reach the REST lookups."""
from pathlib import Path
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from services.annotations import collect_annotations
from services.clinvar import annotate_clinvar_region


APP = Path(__file__).resolve().parents[1] / "app.py"


def empty_snapshot(*args, gene_record_limit, site_record_limit, **kwargs):
    return {
        "values": {("genes",): [], ("exons",): [], ("clinvar",): {
            "search_count": 0, "verified_variants": [], "truncated": False}},
        "errors": {}, "timings": {}, "elapsed_seconds": 0.1,
        "retrieved_at": "test retrieval",
        "search_parameters": {"site_record_limit": site_record_limit,
                              "gene_record_limit": gene_record_limit},
    }


class SearchParameterUITests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.addCleanup(st.cache_data.clear)
        self.addCleanup(st.cache_resource.clear)

    def start_app(self):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertFalse(app.exception, app.exception)
        return app

    def test_defaults_and_collapsed_section_below_analyze(self):
        app = self.start_app()
        self.assertEqual(app.number_input(key="clinvar_site_limit").value, 1000)
        self.assertEqual(app.number_input(key="clinvar_gene_limit").value, 100)
        self.assertEqual(app.number_input(key="clinvar_site_limit").min, 1)
        self.assertIsNone(app.number_input(key="clinvar_site_limit").max)
        self.assertIsNone(app.number_input(key="clinvar_gene_limit").max)
        children = list(app.sidebar.children.values())
        button_index = next(i for i, c in enumerate(children) if getattr(c, "key", None) == "analyze")
        section_index = next(i for i, c in enumerate(children) if getattr(c, "label", None) == "Search Parameters")
        self.assertEqual(section_index, button_index+1)
        self.assertFalse(children[section_index].proto.expanded)

    def test_edits_apply_only_on_analyze_and_captions_use_applied_values(self):
        with patch("services.annotations.collect_annotations", side_effect=empty_snapshot) as lookup:
            app = self.start_app()
            app.button(key="analyze").click().run()
            self.assertEqual(lookup.call_count, 1)
            self.assertEqual(lookup.call_args.kwargs["site_record_limit"], 1000)
            app.number_input(key="clinvar_site_limit").set_value(25)
            app.number_input(key="clinvar_gene_limit").set_value(7).run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(lookup.call_count, 1)
            self.assertEqual(app.session_state["analysis_search_parameters"],
                             {"site_record_limit": 1000, "gene_record_limit": 100})
            self.assertTrue(any("first 100 records" in c.value for c in app.caption))
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(lookup.call_count, 2)
            self.assertEqual(lookup.call_args.kwargs["site_record_limit"], 25)
            self.assertEqual(lookup.call_args.kwargs["gene_record_limit"], 7)
            self.assertTrue(any("first 7 records" in c.value for c in app.caption))
            self.assertTrue(any("up to 25 candidate" in c.value for c in app.caption))
            self.assertEqual(app.session_state["main_tab"], "Site Analysis")

    def test_settings_persist_across_sites_guides_and_empty_filters(self):
        with patch("services.annotations.collect_annotations", side_effect=empty_snapshot) as lookup:
            app = self.start_app()
            app.number_input(key="clinvar_site_limit").set_value(1500)
            app.number_input(key="clinvar_gene_limit").set_value(120).run()
            app.selectbox(key="selected_site").select("SITE-007").run()
            app.slider(key="min_cfd").set_value(1.0).run()
            app.selectbox(key="region_filter").select("Exon").run()
            app.selectbox(key="guide").select("PCSK9-2").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.number_input(key="clinvar_site_limit").value, 1500)
            self.assertEqual(app.number_input(key="clinvar_gene_limit").value, 120)
            self.assertIsNone(app.session_state["analyzed_site"])
            lookup.assert_not_called()
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(lookup.call_args.kwargs["site_record_limit"], 1500)
            self.assertEqual(lookup.call_args.kwargs["gene_record_limit"], 120)

    def test_cache_separates_both_limits_and_reuses_exact_match(self):
        with patch("services.annotations.collect_annotations", side_effect=empty_snapshot) as lookup:
            app = self.start_app()
            for site_limit, gene_limit, expected_calls in [(10, 5, 1), (11, 5, 2), (11, 6, 3), (10, 5, 3)]:
                app.number_input(key="clinvar_site_limit").set_value(site_limit)
                app.number_input(key="clinvar_gene_limit").set_value(gene_limit)
                app.button(key="analyze").click().run()
                self.assertFalse(app.exception, app.exception)
                self.assertEqual(lookup.call_count, expected_calls)
                self.assertTrue(any(f"first {gene_limit} records" in c.value for c in app.caption))


class SearchParameterServiceTests(unittest.TestCase):
    def test_coordinator_passes_each_limit_to_the_right_lookup(self):
        gene = dict(gene_id="TEST", gene_name="TEST", chromosome="1", start=1, end=100)
        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[gene]),
            patch("services.ensembl.get_overlapping_exons", return_value=[]),
            patch("services.ensembl.get_gene_information", return_value=gene),
            patch("services.clinvar.get_ncbi_gene_summary", return_value=None),
            patch("services.clinvar.annotate_clinvar_region", return_value={}) as region,
            patch("services.clinvar.annotate_clinvar_gene", return_value={}) as context,
        ):
            result = collect_annotations("1", 20, 42, gene_record_limit=7, site_record_limit=25)
        self.assertFalse(result["errors"])
        region.assert_called_once_with("1", 20, 42, 25)
        self.assertEqual(context.call_args.kwargs["max_records"], 7)
        self.assertEqual(result["search_parameters"], {"site_record_limit": 25, "gene_record_limit": 7})

    def test_region_annotation_passes_override_to_search(self):
        with patch("services.clinvar.search_clinvar_region", return_value={
            "variant_ids": [], "total_count": 0, "truncated": False}) as search:
            annotate_clinvar_region("1", 20, 42, max_records=25)
        search.assert_called_once_with("1", 20, 42, max_records=25)

    def test_invalid_limits_are_rejected_before_requests(self):
        for site_limit, gene_limit in [(0, 100), (1000, 0), (-1, 1)]:
            with self.subTest(site=site_limit, gene=gene_limit):
                with patch("services.ensembl.get_overlapping_genes") as lookup:
                    with self.assertRaises(ValueError):
                        collect_annotations("1", 20, 42, gene_record_limit=gene_limit,
                                            site_record_limit=site_limit)
                    lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
