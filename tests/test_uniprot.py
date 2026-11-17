"""Offline coverage of protein matching, caching, retries, and independent UI."""
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
from threading import Event

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from services import uniprot
from services.annotation_cache import AnnotationCache
from services.annotations import collect_annotations, retry_uniprot_annotations
from tests.test_parallel_annotations import GENE
from tests.test_search_parameters import APP, empty_snapshot


def entry(accession="P12345", symbol="TEST", taxon=9606, reviewed=True, functions=True):
    return {"primaryAccession": accession, "organism": {"taxonId": taxon},
            "entryType": "UniProtKB reviewed (Swiss-Prot)" if reviewed else "UniProtKB unreviewed (TrEMBL)",
            "genes": [{"geneName": {"value": symbol}, "synonyms": [{"value": "ALIAS"}]}],
            "proteinDescription": {"recommendedName": {"fullName": {"value": "Test protein"}}},
            "comments": [{"commentType": "FUNCTION", "texts": [{"value": "A long protein function. " * 40}]}]
                        if functions else []}


def response(entries, next_url=None):
    result = Mock(status_code=200, headers={}, links={})
    result.json.return_value = {"results": entries}
    if next_url:
        result.links = {"next": {"url": next_url}}
    return result


def protein_result():
    return {"errors": {}, "proteins": [{"accession": "P12345", "protein_name": "Test protein",
            "gene_names": ["TEST"], "functions": ["Normal protein function. " * 40]}],
            "retrieved_at": "test retrieval", "from_cache": False, "rejected_matches": 0}


def protein_page(snapshot, gene):
    from ui.analysis_results import display_uniprot_functions
    display_uniprot_functions(snapshot, gene)


class UniProtServiceTests(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(uniprot, "_cache", AnnotationCache())
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def test_verified_matches_pagination_and_cache(self):
        next_url = uniprot.SEARCH_URL + "?cursor=next"
        with patch.object(uniprot, "uniprot_get", side_effect=[response([
            entry(), entry("P22222", taxon=10090), entry("P33333", symbol="OTHER"),
            entry("P44444", reviewed=False)], next_url), response([entry("P55555")])]) as get:
            result = uniprot.get_protein_functions("TEST")
            self.assertEqual([p["accession"] for p in result["proteins"]], ["P12345", "P55555"])
            self.assertEqual(result["rejected_matches"], 3)
            self.assertEqual(get.call_count, 2)
            self.assertTrue(uniprot.get_protein_functions("test")["from_cache"])
            self.assertEqual(get.call_count, 2)

    def test_synonyms_missing_annotation_and_empty_results(self):
        with patch.object(uniprot, "uniprot_get", return_value=response([entry(functions=False)])):
            self.assertEqual(uniprot.get_protein_functions("ALIAS")["proteins"][0]["functions"], [])
        with patch.object(uniprot, "uniprot_get", return_value=response([])) as get:
            self.assertEqual(uniprot.get_protein_functions("MISSING")["proteins"], [])
            uniprot.get_protein_functions("MISSING")
            self.assertEqual(get.call_count, 1)

    def test_failed_requests_are_not_cached(self):
        with patch.object(uniprot, "uniprot_get", side_effect=[requests.Timeout(), response([entry()])]) as get:
            with self.assertRaises(requests.Timeout):
                uniprot.get_protein_functions("TEST")
            self.assertEqual(len(uniprot.get_protein_functions("TEST")["proteins"]), 1)
            self.assertEqual(get.call_count, 2)

    def test_retries_and_http_timing(self):
        from services.timing import timed_lookup
        good = response([entry()])
        busy = response([])
        busy.status_code = 429
        busy.headers = {"Retry-After": "1"}
        with patch("services.timing.requests.get", side_effect=[busy, good]), \
             patch.object(uniprot._limiter, "wait"), patch.object(uniprot.time, "sleep") as sleep:
            result = timed_lookup(uniprot.get_protein_functions, "TEST")
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(result["requests"][0]["provider"], "UniProt")
        self.assertIn("gene_exact:TEST", result["requests"][0]["query"])
        sleep.assert_called_once_with(1.0)


class UniProtIntegrationTests(unittest.TestCase):
    def test_supplemental_updates_preserve_core_cache_expiry(self):
        cache = AnnotationCache(ttl=10)
        result = {"errors": {}, "values": {}}
        with patch("services.annotation_cache.monotonic", side_effect=[0, 9, 11]):
            cache.put("site", result)
            self.assertIsNotNone(cache.get("site"))
            cache.update("site", {**result, "retried": True})
            self.assertIsNone(cache.get("site"))

    def test_noncoding_and_unnamed_genes_skip_protein_requests(self):
        genes = [{**GENE, "biotype": "lncRNA"},
                 {**GENE, "gene_id": "UNNAMED", "gene_name": "Unknown"}]
        with patch("services.ensembl.get_overlapping_genes", return_value=genes), \
             patch("services.ensembl.get_overlapping_exons", return_value=[]), \
             patch("services.ensembl.get_gene_information", side_effect=lambda gid: next(
                 gene for gene in genes if gene["gene_id"] == gid)), \
             patch("services.clinvar.annotate_clinvar_region", return_value={}), \
             patch("services.clinvar.annotate_clinvar_gene", return_value={}), \
             patch("services.clinvar.get_ncbi_gene_summary", return_value=None), \
             patch.object(uniprot, "get_protein_functions") as proteins:
            result = collect_annotations("1", 20, 42)
        self.assertFalse(result["errors"])
        proteins.assert_not_called()

    def test_progress_and_optional_failure_do_not_block_other_results(self):
        protein_ready = Event()
        snapshots = []
        def slow_region(*args):
            self.assertTrue(protein_ready.wait(3))
            return {}
        def proteins(symbol):
            protein_ready.set()
            return protein_result()
        with patch("services.ensembl.get_overlapping_genes", return_value=[GENE]), \
             patch("services.ensembl.get_overlapping_exons", return_value=[]), \
             patch("services.ensembl.get_gene_information", return_value=GENE), \
             patch("services.clinvar.annotate_clinvar_region", side_effect=slow_region), \
             patch("services.clinvar.annotate_clinvar_gene", return_value={}), \
             patch("services.clinvar.get_ncbi_gene_summary", return_value=None), \
             patch.object(uniprot, "get_protein_functions", side_effect=proteins):
            result = collect_annotations("1", 20, 42, on_update=snapshots.append)
        self.assertFalse(result["errors"])
        self.assertIn(("uniprot", "ENSG_TEST"), result["values"])
        self.assertTrue(any(not s["complete"] and ("uniprot", "ENSG_TEST") in s["values"]
                            for s in snapshots))

    def test_cached_analysis_retries_only_uniprot(self):
        st.cache_resource.clear()
        st.cache_data.clear()
        self.addCleanup(st.cache_resource.clear)
        self.addCleanup(st.cache_data.clear)
        def failed(*args, **kwargs):
            snapshot = empty_snapshot(*args, **kwargs)
            snapshot["values"][("genes",)] = [GENE]
            snapshot["values"][("gene_information", "ENSG_TEST")] = {**GENE, "description": "test"}
            snapshot["errors"][("uniprot", "ENSG_TEST")] = "Timeout"
            return snapshot
        with patch("services.annotations.collect_annotations", side_effect=failed) as collect, \
             patch.object(uniprot, "get_protein_functions", return_value=protein_result()) as protein:
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any("UniProt protein functions are unavailable" in w.value for w in app.warning))
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(collect.call_count, 1)
            protein.assert_called_once_with("TEST")
            self.assertIn("UniProt P12345", [b.label for b in app.get("link_button")])

    def test_render_ready_pending_missing_noncoding_and_multiple(self):
        base = {"values": {}, "errors": {}, "timings": {}, "pending": []}
        key = ("uniprot", "ENSG_TEST")
        for mode in ["pending", "noncoding", "empty", "missing", "multiple"]:
            snapshot = deepcopy(base)
            gene = GENE.copy()
            if mode == "pending":
                snapshot["pending"] = [key]
            elif mode == "noncoding":
                gene["biotype"] = "lncRNA"
            else:
                snapshot["values"][key] = protein_result()
                if mode == "empty":
                    snapshot["values"][key]["proteins"] = []
                elif mode == "missing":
                    snapshot["values"][key]["proteins"][0]["functions"] = []
                else:
                    other = deepcopy(snapshot["values"][key]["proteins"][0])
                    other["accession"] = "P22222"
                    snapshot["values"][key]["proteins"].append(other)
            with self.subTest(mode=mode):
                app = AppTest.from_function(protein_page, args=(snapshot, gene)).run()
                self.assertFalse(app.exception, app.exception)
                if mode == "multiple":
                    self.assertEqual(len(app.get("link_button")), 2)
                    self.assertEqual(len(app.expander), 2)
                    self.assertTrue(app.warning)
                else:
                    self.assertTrue(app.info)


if __name__ == "__main__":
    unittest.main()
