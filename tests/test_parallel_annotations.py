"""Deterministic offline checks for concurrent annotation scheduling."""
import unittest
from threading import Barrier, Event, current_thread
from unittest.mock import patch

import requests

from services.annotations import collect_annotations, annotation_value
from services.rate_limit import RequestRateLimiter


GENE = dict(gene_id="ENSG_TEST", gene_name="TEST", biotype="protein_coding",
            chromosome="1", start=10, end=100, strand=1)


class ParallelAnnotationTests(unittest.TestCase):
    def test_initial_requests_overlap(self):
        rendezvous = Barrier(3, timeout=3)
        threads = set()

        def lookup(value):
            def run(*args):
                threads.add(current_thread().name)
                rendezvous.wait()
                return value
            return run

        with (
            patch("services.ensembl.get_overlapping_genes", side_effect=lookup([])),
            patch("services.ensembl.get_overlapping_exons", side_effect=lookup([])),
            patch("services.clinvar.annotate_clinvar_region", side_effect=lookup({"verified_variants": []})),
            patch("services.ensembl.get_gene_information") as details,
            patch("services.clinvar.annotate_clinvar_gene") as gene_clinvar,
        ):
            result = collect_annotations("1", 20, 42)
        self.assertFalse(result["errors"])
        self.assertEqual(len(threads), 3)
        details.assert_not_called()
        gene_clinvar.assert_not_called()

    def test_gene_work_starts_before_other_region_requests_finish(self):
        summary_started = Event()
        details_and_clinvar = Barrier(2, timeout=3)

        def slow_region(*args):
            self.assertTrue(summary_started.wait(3), "Gene work waited for unrelated region results")
            return []

        def details(gene_id):
            details_and_clinvar.wait()
            return GENE

        def gene_clinvar(**kwargs):
            self.assertEqual(kwargs["max_records"], 5)
            details_and_clinvar.wait()
            return {"gene_variants": []}

        def summary(symbol):
            self.assertEqual(symbol, "TEST")
            summary_started.set()
            return None

        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[GENE]),
            patch("services.ensembl.get_overlapping_exons", side_effect=slow_region),
            patch("services.clinvar.annotate_clinvar_region", side_effect=slow_region),
            patch("services.ensembl.get_gene_information", side_effect=details),
            patch("services.clinvar.annotate_clinvar_gene", side_effect=gene_clinvar),
            patch("services.clinvar.get_ncbi_gene_summary", side_effect=summary),
        ):
            result = collect_annotations("1", 20, 42)
        self.assertFalse(result["errors"])

    def test_failures_preserve_other_results_and_overlap_symbol(self):
        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[GENE]),
            patch("services.ensembl.get_overlapping_exons", side_effect=requests.Timeout("Exon timeout")),
            patch("services.clinvar.annotate_clinvar_region", return_value={"verified_variants": []}),
            patch("services.ensembl.get_gene_information", side_effect=requests.HTTPError("HTTP 500")),
            patch("services.clinvar.annotate_clinvar_gene", side_effect=requests.Timeout("ClinVar timeout")),
            patch("services.clinvar.get_ncbi_gene_summary", return_value=None) as summary,
        ):
            result = collect_annotations("1", 20, 42)
        summary.assert_called_once_with("TEST")
        self.assertEqual(len(result["errors"]), 3)
        self.assertEqual(annotation_value(result, ("genes",)), [GENE])
        self.assertEqual(annotation_value(result, ("clinvar",)), {"verified_variants": []})
        with self.assertRaises(requests.RequestException):
            annotation_value(result, ("exons",))

    def test_duplicate_and_unnamed_genes_do_not_duplicate_or_guess_queries(self):
        unknown = {**GENE, "gene_id": "ENSG_UNKNOWN", "gene_name": "Unknown"}
        with (
            patch("services.ensembl.get_overlapping_genes", return_value=[GENE, GENE, unknown]),
            patch("services.ensembl.get_overlapping_exons", return_value=[]),
            patch("services.clinvar.annotate_clinvar_region", return_value={}),
            patch("services.ensembl.get_gene_information", side_effect=lambda gid: unknown if gid == "ENSG_UNKNOWN" else GENE) as details,
            patch("services.clinvar.annotate_clinvar_gene", return_value={}) as gene_clinvar,
            patch("services.clinvar.get_ncbi_gene_summary", return_value=None) as summary,
        ):
            result = collect_annotations("1", 20, 42)
        self.assertFalse(result["errors"])
        self.assertEqual(details.call_count, 2)
        self.assertEqual(gene_clinvar.call_count, 1)
        summary.assert_called_once_with("TEST")


class RequestRateLimiterTests(unittest.TestCase):
    def test_concurrent_callers_share_one_request_schedule(self):
        from concurrent.futures import ThreadPoolExecutor

        now = [0.0]
        starts = []

        def sleep(delay):
            now[0] += delay

        limiter = RequestRateLimiter(3, clock=lambda: now[0], sleep=sleep)

        def request():
            limiter.wait()
            starts.append(now[0])

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: request(), range(6)))
        self.assertEqual(len(starts), 6)
        self.assertGreaterEqual(now[0], 5 / 3)


if __name__ == "__main__":
    unittest.main()
