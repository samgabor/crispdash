"""Fetch independent site annotations concurrently without calling Streamlit."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from time import perf_counter

from requests.exceptions import RequestException

from services import clinvar, ensembl
from services.timing import timed_lookup


class IncompleteAnnotations(Exception):
    """Carry partial results without caching an unsuccessful analysis."""
    def __init__(self, results):
        super().__init__("Some annotation lookups failed")
        self.results = results


def annotation_value(results, key):
    """Read a completed lookup, preserving failed versus empty results."""
    if key in results["errors"]:
        raise RequestException(results["errors"][key])
    return results["values"][key]


def has_gene_symbol(symbol):
    return bool(symbol and str(symbol).strip().lower() != "unknown")


def collect_annotations(chrom, start, end):
    """Start dependent lookups as soon as their own prerequisite completes.

    The coordinator owns all result dictionaries. Workers only run the existing
    REST service functions, whose shared rate limiters pace every request.
    """
    started = perf_counter()
    results = {"values": {}, "errors": {}, "timings": {}}
    genes_by_id = {}
    scheduled = set()
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="annotations") as pool:
        pending = {}

        def submit(key, function, *args, **kwargs):
            if key not in scheduled:
                scheduled.add(key)
                pending[pool.submit(timed_lookup, function, *args, **kwargs)] = key

        submit(("genes",), ensembl.get_overlapping_genes, chrom, start, end)
        submit(("exons",), ensembl.get_overlapping_exons, chrom, start, end)
        submit(("clinvar",), clinvar.annotate_clinvar_region, chrom, start, end)

        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                key = pending.pop(future)
                outcome = future.result()
                value = outcome["value"]
                results["timings"][key] = {
                    "elapsed_seconds": outcome["elapsed_seconds"],
                    "requests": outcome["requests"],
                }
                if outcome["error"] is not None:
                    results["errors"][key] = outcome["error"]
                else:
                    results["values"][key] = value

                if key == ("genes",) and value:
                    for gene in value:
                        gene_id = gene["gene_id"]
                        genes_by_id[gene_id] = gene
                        submit(("gene_information", gene_id),
                               ensembl.get_gene_information, gene_id)
                        symbol = gene.get("gene_name")
                        if has_gene_symbol(symbol):
                            submit(
                                ("gene_clinvar", gene_id), clinvar.annotate_clinvar_gene,
                                gene_symbol=symbol, site_chrom=chrom,
                                site_start=start, site_end=end,
                                gene_chrom=gene["chromosome"],
                                gene_start=int(gene["start"]),
                                gene_end=int(gene["end"]), max_records=5,
                            )

                elif key[0] == "gene_information":
                    # A failed details request can still leave a useful symbol
                    # in the successful overlap response, as in the UI fallback.
                    metadata = value or genes_by_id[key[1]]
                    symbol = metadata.get("gene_name")
                    if has_gene_symbol(symbol):
                        submit(("ncbi_summary", symbol),
                               clinvar.get_ncbi_gene_summary, symbol)

    results["elapsed_seconds"] = perf_counter() - started
    results["retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return results
