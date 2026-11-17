"""Reviewed human protein functions, matched by exact gene name or synonym."""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from services.annotation_cache import AnnotationCache
from services.rate_limit import RequestRateLimiter
from services.timing import timed_get

SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
_limiter = RequestRateLimiter(5)
_cache = AnnotationCache(ttl=3600)


def uniprot_get(url, params=None):
    for attempt in range(3):
        try:
            _limiter.wait()
            response = timed_get("UniProt", url, params=params,
                                 headers={"Accept": "application/json"}, timeout=20)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                retry_after = response.headers.get("Retry-After", "")
                delay = min(float(retry_after), 30) if retry_after.isdigit() else 2 ** attempt
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("UniProt request did not complete")


def get_protein_functions(gene_symbol):
    symbol = str(gene_symbol).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", symbol):
        raise ValueError("A recognized gene symbol is required for UniProt matching.")
    cached = _cache.get(symbol.casefold())
    if cached is not None:
        return {**cached, "from_cache": True}
    params = {
        "query": f"gene_exact:{symbol} AND organism_id:9606 AND reviewed:true",
        "format": "json", "size": 100,
        "fields": "accession,protein_name,gene_names,organism_id,reviewed,cc_function",
    }
    proteins, rejected, seen = [], 0, set()
    url = SEARCH_URL
    while url:
        if url in seen:
            raise ValueError("UniProt returned a repeated results page.")
        seen.add(url)
        response = uniprot_get(url, params)
        payload = response.json()
        if not isinstance(payload.get("results"), list):
            raise ValueError("UniProt returned an unexpected response.")
        for entry in payload["results"]:
            names = [name.get("value", "") for gene in entry.get("genes", [])
                     for name in [gene.get("geneName", {}), *gene.get("synonyms", [])]]
            accession = entry.get("primaryAccession", "")
            if (entry.get("organism", {}).get("taxonId") != 9606 or
                entry.get("entryType") != "UniProtKB reviewed (Swiss-Prot)" or
                symbol.casefold() not in {name.casefold() for name in names} or
                not re.fullmatch(r"[A-Z0-9]+", accession)):
                rejected += 1
                continue
            if any(p["accession"] == accession for p in proteins):
                continue
            description = entry.get("proteinDescription", {})
            protein_name = description.get("recommendedName", {}).get("fullName", {}).get("value")
            if not protein_name:
                protein_name = next((n.get("fullName", {}).get("value") for n in
                                     description.get("submissionNames", [])), "Name unavailable")
            functions = [text["value"] for comment in entry.get("comments", [])
                         if comment.get("commentType") == "FUNCTION"
                         for text in comment.get("texts", []) if text.get("value")]
            proteins.append({"accession": accession, "protein_name": protein_name,
                             "functions": functions, "gene_names": names})
        url = response.links.get("next", {}).get("url")
        params = None
        if url and (urlsplit(url).scheme != "https" or
                    urlsplit(url).netloc != "rest.uniprot.org" or
                    urlsplit(url).path != "/uniprotkb/search"):
            raise ValueError("UniProt returned an unexpected pagination link.")
    result = {"errors": {}, "proteins": proteins, "rejected_matches": rejected,
              "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "from_cache": False}
    _cache.put(symbol.casefold(), result)
    return result
