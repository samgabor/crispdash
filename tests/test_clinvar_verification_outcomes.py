"""Deterministic verification and UI checks; no live NCBI requests."""
import unittest
from unittest.mock import Mock, patch

import requests
from streamlit.testing.v1 import AppTest

from services import clinvar
from services.annotations import collect_annotations


def variant(classification="Pathogenic", start=120, end=None, chrom="1", assembly="GRCh38"):
    if end is None:
        end = start
    return {
        "title": "Test variant",
        "germline_classification": {"description": classification, "review_status": "reviewed"},
        "variation_set": [{"variation_loc": [{
            "assembly_name": assembly, "chr": chrom, "start": start, "stop": end,
        }]}],
    }


def annotate(records, total=None, **kwargs):
    ids = [str(i) for i in range(len(records))]
    with (
        patch.object(clinvar, "search_clinvar_gene_pathogenic", return_value={
            "total_count": len(ids) if total is None else total, "variant_ids": ids}),
        patch.object(clinvar, "get_clinvar_variant_details", side_effect=records),
    ):
        params = dict(gene_symbol="TEST", site_chrom="chr1", site_start=150,
                      site_end=160, gene_chrom="1", gene_start=100, gene_end=200)
        params.update(kwargs)
        return clinvar.annotate_clinvar_gene(**params)


def verification_ui(result, debug):
    import config
    from ui.analysis_results import display_clinvar_verification
    from unittest.mock import patch
    with patch.object(config, "DEBUG", debug):
        display_clinvar_verification(result)


class VerificationOutcomeTests(unittest.TestCase):
    def assert_reconciles(self, result):
        self.assertEqual(result["records_examined"], result["excluded_count"] +
                         result["direct_overlap_count"] + result["verified_elsewhere_count"])
        self.assertEqual(result["records_examined"], len(result["verification_outcomes"]))

    def test_all_outcomes_and_strict_classifications(self):
        records = [variant(), variant("Likely pathogenic"), variant(start=150),
                   variant(start=201), variant(assembly="GRCh37"),
                   variant("Uncertain significance"), variant("Pathogenic/Likely pathogenic"),
                   variant("Conflicting classifications of pathogenicity"), variant(chrom="2")]
        result = annotate(records)
        self.assertEqual(result["verified_elsewhere_count"], 2)
        self.assertEqual(result["direct_overlap_count"], 1)
        self.assertEqual(result["outside_gene_count"], 2)
        self.assertEqual(result["missing_grch38_count"], 1)
        self.assertEqual(result["classification_excluded_count"], 3)
        self.assertEqual(result["verification_outcomes"][6]["clinical_significance"],
                         "Pathogenic/Likely pathogenic")
        self.assert_reconciles(result)

    def test_unavailable_boundaries_and_precedence(self):
        for boundaries in [dict(gene_start=None), dict(gene_chrom=""), dict(gene_end=99),
                           dict(gene_start="bad"), dict(gene_start=1.5)]:
            with self.subTest(boundaries=boundaries):
                result = annotate([variant(), variant(start=150),
                                   variant(assembly="GRCh37"), variant("Uncertain significance")],
                                  **boundaries)
                self.assertFalse(result["gene_boundaries_available"])
                self.assertEqual(result["missing_gene_boundaries_count"], 1)
                self.assertEqual(result["direct_overlap_count"], 1)
                self.assertEqual(result["missing_grch38_count"], 1)
                self.assertEqual(result["classification_excluded_count"], 1)
                self.assert_reconciles(result)

    def test_invalid_locations(self):
        for args in [dict(start=0), dict(start="bad"), dict(start=120.5), dict(end=100), dict(chrom=""),
                     dict(start=None), dict(assembly="GRCh37")]:
            with self.subTest(args=args):
                result = annotate([variant(**args)])
                self.assertEqual(result["missing_grch38_count"], 1)
                self.assert_reconciles(result)

    def test_inclusive_edges_and_chromosome_normalization(self):
        result = annotate([variant(start=100), variant(start=200, chrom="chr1"),
                           variant(start=149, end=150), variant(start=160)])
        self.assertEqual(result["verified_elsewhere_count"], 2)
        self.assertEqual(result["direct_overlap_count"], 2)
        self.assert_reconciles(result)

    def test_multiple_locations_still_assign_one_outcome(self):
        record = variant()
        record["variation_set"].extend(variant(start=150)["variation_set"])
        result = annotate([record])
        self.assertEqual(result["direct_overlap_count"], 1)
        self.assertEqual(result["verified_elsewhere_count"], 0)
        self.assert_reconciles(result)

    def test_empty_and_truncated(self):
        result = annotate([])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["records_examined"], 0)
        self.assert_reconciles(result)
        result = annotate([variant()], total=2500)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["records_retrieved"], 1)
        self.assert_reconciles(result)

    def test_search_returns_retrieval_metadata(self):
        response = Mock()
        response.json.return_value = {"esearchresult": {"count": "2500", "idlist": ["1", "2"]}}
        with patch.object(clinvar, "ncbi_get", return_value=response) as get:
            result = clinvar.search_clinvar_gene_pathogenic("TEST", max_records=100)
        self.assertEqual(result["records_retrieved"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(get.call_args.kwargs["params"]["retmax"], 100)

    def test_request_failure_is_not_an_exclusion(self):
        with self.assertRaises(requests.Timeout):
            annotate([requests.Timeout("record unavailable")])

    def test_coordinator_passes_missing_boundaries_without_crashing(self):
        gene = dict(gene_id="GENE", gene_name="TEST", chromosome="1", start=None, end=200)
        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[gene]),
            patch("services.ensembl.get_overlapping_exons", return_value=[]),
            patch("services.ensembl.get_gene_information", return_value=gene),
            patch.object(clinvar, "get_ncbi_gene_summary", return_value=None),
            patch.object(clinvar, "annotate_clinvar_region", return_value={}),
            patch.object(clinvar, "annotate_clinvar_gene", return_value={}) as query,
        ):
            result = collect_annotations("1", 150, 160)
        self.assertFalse(result["errors"])
        self.assertIsNone(query.call_args.kwargs["gene_start"])
        self.assertEqual(query.call_args.kwargs["gene_end"], 200)


class VerificationUITests(unittest.TestCase):
    def test_breakdown_and_debug_visibility(self):
        result = annotate([variant("Pathogenic/Likely pathogenic")])
        for debug in [False, True]:
            with self.subTest(debug=debug):
                app = AppTest.from_function(verification_ui, args=(result, debug)).run()
                self.assertFalse(app.exception)
                self.assertIn("ClinVar Verification Details", [e.label for e in app.expander])
                self.assertEqual(len(app.dataframe), 2 if debug else 1)
                if debug:
                    self.assertEqual(app.dataframe[1].value.iloc[0]["Original classification"],
                                     "Pathogenic/Likely pathogenic")
                self.assertTrue(any("does not establish" in e.value for e in app.info))

    def test_truncation_and_missing_boundary_warnings(self):
        result = annotate([variant()], total=2500, gene_start=None)
        app = AppTest.from_function(verification_ui, args=(result, False)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("1 of 2500" in w.value for w in app.warning))
        self.assertTrue(any("boundaries were unavailable" in w.value for w in app.warning))


if __name__ == "__main__":
    unittest.main()
