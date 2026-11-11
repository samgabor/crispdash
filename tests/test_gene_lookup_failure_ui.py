"""Offline regression coverage for unavailable Ensembl gene details."""
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from services.ensembl import get_gene_information


APP = Path(__file__).resolve().parents[1] / "app.py"
FAILED_ID = "ENSG00000229876"


def overlap(gene_id, name="Unknown"):
    return dict(gene_id=gene_id, gene_name=name, biotype="lncRNA",
                chromosome="1", start=100, end=200, strand=1)


class GeneLookupFailureTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.addCleanup(st.cache_data.clear)
        self.addCleanup(st.cache_resource.clear)

    def run_analysis(self, genes, lookup, gene_clinvar_error=None):
        with (
            patch("services.ensembl.get_overlapping_genes", return_value=genes),
            patch("services.ensembl.get_overlapping_exons", return_value=[]),
            patch("services.ensembl.get_gene_information", side_effect=lookup),
            patch("services.clinvar.get_ncbi_gene_summary", return_value=None),
            patch("services.clinvar.annotate_clinvar_region", return_value={
                "verified_variants": [], "search_count": 0, "truncated": False}),
            patch("services.clinvar.annotate_clinvar_gene", side_effect=gene_clinvar_error, return_value={
                "search_count": 0, "records_examined": 0, "gene_variants": []}),
        ):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            app.button(key="analyze").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any(s.value == "Integrated evidence summary" for s in app.subheader))
        self.assertEqual([tab.label for tab in app.tabs][2:], [
            "Site Details", "Genes & Function", "Exons", "ClinVar Site Overlaps",
            "ClinVar Gene Context", "Evidence Summary",
        ])
        return app

    def test_failed_clinvar_gene_lookup_is_unavailable_not_zero(self):
        gene = overlap(FAILED_ID, "TEST")
        app = self.run_analysis([gene], lambda _: {**gene, "description": "Gene details"},
                                requests.Timeout("Gene ClinVar timeout"))
        summaries = [table.value for table in app.dataframe
                     if "Evidence Category" in table.value.columns]
        findings = summaries[0].set_index("Evidence Category")["Finding"]
        self.assertEqual(findings["Gene-Level ClinVar Search Matches"], "Unavailable (incomplete lookup)")
        self.assertEqual(findings["Direct ClinVar Variant Overlaps"], "0")

    def test_variants_from_multiple_genes_share_one_linked_table(self):
        first = overlap("ENSG_FIRST", "FIRST")
        second = overlap("ENSG_SECOND", "SECOND")
        shared = dict(variant_id="7105", title="NM_000110.4(DPYD):c.1132G>T (p.Glu378Ter)",
                      clinical_significance="Pathogenic", review_status="criteria provided, single submitter")
        other = {**shared, "variant_id": "7106", "title": "NM_000110.4(DPYD):c.2883_2884insTAAATG (p.Thr962Ter)"}

        def gene_result(**kwargs):
            variants = [shared] if kwargs["gene_symbol"] == "FIRST" else [shared, other]
            return dict(search_count=2, records_examined=2, gene_variants=variants)

        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[first, second]),
            patch("services.ensembl.get_overlapping_exons", return_value=[]),
            patch("services.ensembl.get_gene_information", side_effect=lambda gid: {
                **(first if gid == "ENSG_FIRST" else second), "description": "Gene details"}),
            patch("services.clinvar.get_ncbi_gene_summary", return_value=None),
            patch("services.clinvar.annotate_clinvar_region", return_value={
                "verified_variants": [], "search_count": 0, "truncated": False}),
            patch("services.clinvar.annotate_clinvar_gene", side_effect=gene_result),
        ):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            app.button(key="analyze").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(app.table), 1)
        table = app.table[0].value
        self.assertEqual(table.columns.tolist(), ["Variant", "Clinical significance", "Review status"])
        self.assertEqual(len(table), 2)
        self.assertIn("https://www.ncbi.nlm.nih.gov/clinvar/variation/7105/", table.iloc[0]["Variant"])
        self.assertIn("p.Glu378Ter", table.iloc[0]["Variant"])
        self.assertIn("https://www.ncbi.nlm.nih.gov/clinvar/variation/7106/", table.iloc[1]["Variant"])

    def test_exhausted_http_500_retries_do_not_crash_analysis(self):
        response = requests.Response()
        response.status_code = 500
        response.url = f"https://rest.ensembl.org/lookup/id/{FAILED_ID}"
        with patch("services.ensembl.requests.get", return_value=response) as get:
            app = self.run_analysis([overlap(FAILED_ID)], get_gene_information)
        self.assertEqual(get.call_count, 3)
        self.assertTrue(any(FAILED_ID in w.value for w in app.warning))
        self.assertTrue(any("Detailed description unavailable" in m.value for m in app.markdown))

    def test_failed_gene_does_not_block_other_gene_details(self):
        healthy = {**overlap("ENSG_HEALTHY", "GENE2"), "description": "Healthy gene details"}

        def lookup(gene_id):
            if gene_id == FAILED_ID:
                raise requests.Timeout("Simulated Ensembl timeout")
            return healthy

        app = self.run_analysis([overlap(FAILED_ID), overlap("ENSG_HEALTHY", "GENE2")], lookup)
        self.assertTrue(any("Healthy gene details" in m.value for m in app.markdown))

    def test_failed_lookup_is_retried_and_warning_clears_after_recovery(self):
        gene = overlap(FAILED_ID)
        recovered = {**gene, "description": "Recovered details"}
        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[gene]),
            patch("services.ensembl.get_overlapping_exons", return_value=[]),
            patch("services.ensembl.get_gene_information", side_effect=[
                requests.Timeout("Temporary outage"), recovered]) as lookup,
            patch("services.clinvar.annotate_clinvar_region", return_value={
                "verified_variants": [], "search_count": 0, "truncated": False}),
        ):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            # A complete analysis is cached on subsequent page interactions.
            app.run()
            self.assertFalse(app.exception, app.exception)
        self.assertEqual(lookup.call_count, 2)
        self.assertFalse(any(FAILED_ID in w.value for w in app.warning))
        self.assertTrue(any("Recovered details" in m.value for m in app.markdown))


if __name__ == "__main__":
    unittest.main()
