import os
import time
import requests

from config import NCBI_API_KEY
from services.rate_limit import RequestRateLimiter
from services.timing import timed_get

NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_request_limiter = RequestRateLimiter(10 if NCBI_API_KEY else 3)

def ncbi_get(url, params, max_attempts=4):
    """
    Make an NCBI API request with retries for temporary failures.

    Retries:
    - HTTP 429: Too Many Requests
    - HTTP 500, 502, 503, 504: Server errors
    - Connection errors and timeouts

    Other HTTP errors are raised immediately.
    """

    retry_statuses = {429, 500, 502, 503, 504}

    for attempt in range(max_attempts):

        try:

            # Include the NCBI API key when available
            request_params = dict(params or {})

            if NCBI_API_KEY:
                request_params["api_key"] = NCBI_API_KEY

            _request_limiter.wait()
            response = timed_get(
                "NCBI", url,
                params=request_params,
                timeout=30
            )

            if response.status_code in retry_statuses:

                if attempt == max_attempts - 1:
                    response.raise_for_status()

                # Wait progressively longer between retries
                wait_seconds = 2 ** attempt

                print(
                    f"NCBI returned HTTP "
                    f"{response.status_code}. "
                    f"Retrying in {wait_seconds} seconds..."
                )

                time.sleep(wait_seconds)
                continue

            response.raise_for_status()

            return response

        except (requests.Timeout, requests.ConnectionError):

            if attempt == max_attempts - 1:
                raise

            wait_seconds = 2 ** attempt

            print(
                f"NCBI connection issue. "
                f"Retrying in {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)


def search_clinvar_region(chrom, start, end, max_records=1000):
    """
    Search ClinVar for candidate variants using GRCh38 coordinates.

    Retrieves results in pages of 100 records.

    Parameters
    ----------
    chrom : str
        Chromosome name, such as "1" or "chr1".
    start, end : int
        GRCh38 genomic coordinates (1-based inclusive).
    max_records : int
        Maximum number of candidate IDs to retrieve.

    Returns
    -------
    dict
        total_count: Total records reported by ClinVar
        variant_ids: Retrieved candidate IDs
        search_term: Query submitted to ClinVar
        truncated: Whether some candidate IDs were not retrieved
    """

    chrom = str(chrom).removeprefix("chr")
    start = int(start)
    end = int(end)

    if start < 1 or end < start:
        raise ValueError("Invalid genomic coordinates.")

    if max_records < 1:
        raise ValueError("max_records must be at least 1.")

    search_term = (
        f"{chrom}[chr] AND {start}:{end}[chrpos38]"
    )

    url = f"{NCBI_BASE_URL}/esearch.fcgi"

    variant_ids = []
    total_count = None
    page_size = 100

    while True:

        remaining = max_records - len(variant_ids)

        if remaining <= 0:
            break

        params = {
            "db": "clinvar",
            "term": search_term,
            "retmode": "json",
            "retstart": len(variant_ids),
            "retmax": min(page_size, remaining),
            "tool": "crispr_offtarget_dashboard",
        }

        email = os.getenv("NCBI_EMAIL")

        if email:
            params["email"] = email

        response = ncbi_get(url, params)

        result = response.json()["esearchresult"]

        total_count = int(result["count"])

        page_ids = result["idlist"]

        if not page_ids:
            break

        variant_ids.extend(page_ids)

        if len(variant_ids) >= total_count:
            break

        # ncbi_get applies the shared request limiter to every page.

    return {
        "total_count": total_count,
        "variant_ids": variant_ids,
        "search_term": search_term,
        "truncated": len(variant_ids) < total_count,
    }



def get_clinvar_variant_details(variant_id):
    """
    Retrieve a ClinVar variant summary using NCBI ESummary.

    Parameters
    ----------
    variant_id : str or int
        NCBI ClinVar Variation ID.

    Returns
    -------
    dict
        Raw ClinVar variant summary.
    """

    url = f"{NCBI_BASE_URL}/esummary.fcgi"

    params = {
        "db": "clinvar",
        "id": str(variant_id),
        "retmode": "json",
        "tool": "crispr_offtarget_dashboard",
    }

    email = os.getenv("NCBI_EMAIL")

    if email:
        params["email"] = email

    response = ncbi_get(url, params)

    # response = requests.get(
    #     url,
    #     params=params,
    #     timeout=20
    # )
    #
    # response.raise_for_status()

    result = response.json()

    variant = result["result"][str(variant_id)]

    return variant

def extract_grch38_locations(variant):
    """
    Extract GRCh38 genomic locations from a ClinVar ESummary record.

    Parameters
    ----------
    variant : dict
        ClinVar ESummary variant record.

    Returns
    -------
    list
        GRCh38 genomic locations with integer coordinates.
    """

    locations = []

    for measure in variant.get("variation_set", []):

        for location in measure.get("variation_loc", []):

            # Only use GRCh38 coordinates
            if location.get("assembly_name") != "GRCh38":
                continue

            chrom = location.get("chr")
            start = location.get("start")
            end = location.get("stop")

            # Skip incomplete coordinates
            if not chrom or not start or not end:
                continue

            try:
                start = int(start)
                end = int(end)
            except (ValueError, TypeError):
                continue

            # Skip invalid intervals
            if start < 1 or end < start:
                continue

            locations.append({
                "chromosome": str(chrom),
                "start": start,
                "end": end,
                "assembly": "GRCh38",
                "status": location.get("status"),
                "variation_name": measure.get("variation_name"),
                "variant_type": measure.get("variant_type"),
            })

    return locations

def check_genomic_overlap(
    site_chrom,
    site_start,
    site_end,
    variant_location
):
    """
    Check whether a ClinVar GRCh38 location overlaps
    a CRISPR off-target site.

    Both intervals must use GRCh38 and
    1-based inclusive coordinates.

    Returns True if they overlap, otherwise False.
    """

    # Ensure the ClinVar location uses GRCh38
    if variant_location.get("assembly") != "GRCh38":
        return False

    # Normalize chromosome names
    site_chrom = str(site_chrom).removeprefix("chr")
    variant_chrom = str(
        variant_location["chromosome"]
    ).removeprefix("chr")

    # Different chromosomes cannot overlap
    if site_chrom != variant_chrom:
        return False

    # Convert coordinates to integers
    site_start = int(site_start)
    site_end = int(site_end)

    variant_start = int(variant_location["start"])
    variant_end = int(variant_location["end"])

    # Validate intervals
    if (
        site_start < 1
        or variant_start < 1
        or site_end < site_start
        or variant_end < variant_start
    ):
        raise ValueError("Invalid genomic coordinates.")

    # Check interval overlap
    return (
        variant_start <= site_end
        and variant_end >= site_start
    )

def annotate_clinvar_region(chrom, start, end):
    """
    Search ClinVar and verify GRCh38 genomic overlaps.

    Returns:
        search_count: Number of candidate records found
        verified_variants: Variants with confirmed GRCh38 overlap
        truncated: Whether the search returned more records
                   than the current 100-record retrieval limit
    """

    search_result = search_clinvar_region(chrom, start, end)

    variant_ids = search_result["variant_ids"]
    verified_variants = []

    for variant_id in variant_ids:

        variant = get_clinvar_variant_details(variant_id)

        locations = extract_grch38_locations(variant)

        overlapping_locations = []

        for location in locations:

            if check_genomic_overlap(
                site_chrom=chrom,
                site_start=start,
                site_end=end,
                variant_location=location
            ):
                overlapping_locations.append(location)

        if not overlapping_locations:
            continue

        classification = variant.get(
            "germline_classification", {}
        )

        traits = classification.get("trait_set", [])

        condition_names = [
            trait.get("trait_name")
            for trait in traits
            if trait.get("trait_name")
        ]

        verified_variants.append({
            "clinvar_id": variant_id,
            "accession": variant.get("accession"),
            "variant_name": variant.get("title"),
            "clinical_significance": classification.get(
                "description", "Not provided"
            ),
            "review_status": classification.get(
                "review_status", "Not provided"
            ),
            "conditions": ", ".join(condition_names),
            "locations": overlapping_locations,
        })

    return {
        "search_count": search_result["total_count"],
        "verified_variants": verified_variants,
        "truncated": search_result["truncated"],
    }

def search_clinvar_gene(gene_symbol, max_records=10):
    """
    Search ClinVar for records associated with a gene.

    This is a gene-level search, not an exact
    genomic-coordinate overlap search.
    """

    url = f"{NCBI_BASE_URL}/esearch.fcgi"

    search_term = f"{gene_symbol}[gene]"

    params = {
        "db": "clinvar",
        "term": search_term,
        "retmode": "json",
        "retmax": max_records
    }

    response = ncbi_get(url, params=params)

    data = response.json()

    search_result = data.get("esearchresult", {})

    return {
        "gene": gene_symbol,
        "total_count": int(
            search_result.get("count", 0)
        ),
        "variant_ids": search_result.get(
            "idlist", []
        ),
        "search_term": search_term
    }


def search_clinvar_gene_pathogenic(gene_symbol, max_records=10):
    """
    Search ClinVar for variants associated with a gene
    that have pathogenic or likely pathogenic
    germline classifications.

    This does not establish overlap with an off-target site.
    """

    url = f"{NCBI_BASE_URL}/esearch.fcgi"

    search_term = (
        f"{gene_symbol}[gene] AND "
        f'("clinsig pathogenic"[Properties] OR '
        f'"clinsig likely pathogenic"[Properties])'
    )

    params = {
        "db": "clinvar",
        "term": search_term,
        "retmode": "json",
        "retmax": max_records
    }

    response = ncbi_get(url, params=params)

    data = response.json()

    search_result = data.get("esearchresult", {})

    return {
        "gene": gene_symbol,
        "total_count": int(
            search_result.get("count", 0)
        ),
        "variant_ids": search_result.get("idlist", []),
        "search_term": search_term
    }

def annotate_clinvar_gene(
    gene_symbol,
    site_chrom,
    site_start,
    site_end,
    gene_chrom=None,
    gene_start=None,
    gene_end=None,
    max_records=5
):
    """
    Retrieve a sample of clinically relevant ClinVar
    variants associated with a gene.

    Distinguish variants overlapping the selected
    off-target site from variants elsewhere.
    """

    search_result = search_clinvar_gene_pathogenic(
        gene_symbol,
        max_records=max_records
    )

    gene_variants = []
    direct_overlaps = []
    excluded_count = 0

    for variant_id in search_result["variant_ids"]:

        variant = get_clinvar_variant_details(variant_id)

        clinical = variant.get(
            "germline_classification", {}
        )

        significance = clinical.get(
            "description", ""
        ).strip()

        # Verify the displayed aggregate classification
        if significance.lower() not in {
            "pathogenic",
            "likely pathogenic"
        }:
            excluded_count += 1
            continue

        locations = extract_grch38_locations(variant)

        if not locations:
            excluded_count += 1
            continue

        overlaps_site = any(
            check_genomic_overlap(
                site_chrom,
                site_start,
                site_end,
                location
            )
            for location in locations
        )

        variant_info = {
            "variant_id": variant_id,
            "title": variant.get(
                "title", "Not available"
            ),
            "clinical_significance": significance,
            "review_status": clinical.get(
                "review_status", "Not available"
            ),
            "locations": locations
        }

        if overlaps_site:
            direct_overlaps.append(variant_info)

        else:
            # Check whether the variant overlaps
            # the Ensembl gene boundaries.
            if (
                    gene_chrom is not None
                    and gene_start is not None
                    and gene_end is not None
            ):
                within_gene = any(
                    str(location["chromosome"]).removeprefix("chr")
                    == str(gene_chrom).removeprefix("chr")
                    and location["start"] <= gene_end
                    and location["end"] >= gene_start
                    for location in locations
                )

                if within_gene:
                    gene_variants.append(variant_info)
                else:
                    excluded_count += 1

            else:
                # Gene boundaries were not supplied.
                # Do not claim the variant is within the gene.
                excluded_count += 1

    return {
        "gene": gene_symbol,
        "search_count": search_result["total_count"],
        "records_examined": len(
            search_result["variant_ids"]
        ),
        "gene_variants": gene_variants,
        "direct_overlaps": direct_overlaps,
        "excluded_count": excluded_count
    }

def get_ncbi_gene_summary(gene_symbol):
    """
    Retrieve a biological gene summary from NCBI Gene.

    Returns a dictionary or None if no reliable
    matching gene record is found.
    """

    # Search NCBI Gene for an exact human gene symbol.
    search_url = f"{NCBI_BASE_URL}/esearch.fcgi"

    search_params = {
        "db": "gene",
        "term": f'{gene_symbol}[sym] AND 9606[Taxonomy ID]',
        "retmode": "json",
        "retmax": 10,
    }

    response = ncbi_get(search_url, search_params)
    search_data = response.json()

    gene_ids = search_data.get("esearchresult", {}).get("idlist", [])

    if not gene_ids:
        return None

    # Retrieve matching gene records.
    summary_url = f"{NCBI_BASE_URL}/esummary.fcgi"

    summary_params = {
        "db": "gene",
        "id": ",".join(gene_ids),
        "retmode": "json",
    }

    response = ncbi_get(summary_url, summary_params)
    summary_data = response.json().get("result", {})

    # Verify the returned symbol matches the requested symbol.
    for gene_id in gene_ids:

        gene = summary_data.get(str(gene_id), {})

        if gene.get("name", "").upper() != gene_symbol.upper():
            continue

        return {
            "gene_id": str(gene_id),
            "gene_symbol": gene.get("name"),
            "full_name": gene.get("description"),
            "biological_summary": gene.get("summary")
            or "No biological summary available.",
        }

    return None
