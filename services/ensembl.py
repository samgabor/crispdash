import time
import requests
from services.rate_limit import RequestRateLimiter
from services.timing import timed_get

ENSEMBL_BASE_URL = "https://rest.ensembl.org"
_request_limiter = RequestRateLimiter(15)


def ensembl_get(url, params=None, max_attempts=3):
    """
    Make an Ensembl API request with automatic retries.

    Retries temporary server errors, rate limiting,
    connection failures, and timeouts.
    """

    retry_statuses = {429, 500, 502, 503, 504}

    headers = {
        "Accept": "application/json"
    }

    for attempt in range(max_attempts):

        try:
            _request_limiter.wait()
            response = timed_get(
                "Ensembl", url,
                params=params,
                headers=headers,
                timeout=60
            )

            if response.status_code in retry_statuses:

                if attempt == max_attempts - 1:
                    response.raise_for_status()

                wait_seconds = 2 ** attempt

                print(
                    f"Ensembl returned HTTP "
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
                "Ensembl connection issue. "
                f"Retrying in {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)


def get_overlapping_genes(chrom, start, end):
    """
    Retrieve genes overlapping a genomic region.

    Reference assembly: GRCh38
    Coordinate convention: 1-based inclusive

    Parameters
    ----------
    chrom : str
        Chromosome name, e.g. "chr1".

    start : int
        Start coordinate.

    end : int
        End coordinate.

    Returns
    -------
    list
        List of overlapping gene annotations.
    """

    # Ensembl expects chromosome names without "chr"
    chrom = str(chrom).removeprefix("chr")

    # Construct genomic region
    region = f"{chrom}:{int(start)}-{int(end)}"

    # Ensembl overlap endpoint
    url = (
        f"{ENSEMBL_BASE_URL}"
        f"/overlap/region/human/{region}"
    )

    # Request gene annotations
    response = ensembl_get(url, params={"feature": "gene"})
    # response = requests.get(
    #     url,
    #     params={"feature": "gene"},
    #     headers={"Accept": "application/json"},
    #     timeout=60
    # )
    #
    # # Raise an exception if the API request fails
    # response.raise_for_status()

    # Parse JSON response
    genes = response.json()

    # Extract useful fields
    results = []

    for gene in genes:
        results.append(
            {
                "gene_id": gene.get("id"),
                "gene_name": gene.get(
                    "external_name",
                    "Unknown"
                ),
                "biotype": gene.get("biotype"),
                "chromosome": gene.get("seq_region_name"),
                "start": gene.get("start"),
                "end": gene.get("end"),
                "strand": gene.get("strand"),
            }
        )

    return results

def get_overlapping_exons(chrom, start, end):
    """
    Retrieve Ensembl exons overlapping a genomic region.

    Reference assembly: GRCh38
    Coordinate convention: 1-based inclusive

    Returns
    -------
    list
        List of overlapping exon annotations.
    """

    chrom = str(chrom).removeprefix("chr")

    region = f"{chrom}:{int(start)}-{int(end)}"

    url = (
        f"{ENSEMBL_BASE_URL}"
        f"/overlap/region/human/{region}"
    )

    # response = requests.get(
    #     url,
    #     params={"feature": "exon"},
    #     headers={"Accept": "application/json"},
    #     timeout=60
    # )
    # response.raise_for_status()

    response = ensembl_get(url, params={"feature": "exon"})




    exons = response.json()

    results = []

    for exon in exons:
        results.append(
            {
                "exon_id": exon.get("id"),
                "chromosome": exon.get("seq_region_name"),
                "start": exon.get("start"),
                "end": exon.get("end"),
                "strand": exon.get("strand"),
            }
        )

    # Remove duplicate exon annotations
    unique_exons = []

    seen_exon_ids = set()

    for exon in results:

        exon_id = exon["exon_id"]

        if exon_id not in seen_exon_ids:
            unique_exons.append(exon)

            seen_exon_ids.add(exon_id)

    return unique_exons

def get_gene_information(gene_id):
    """
    Retrieve detailed gene information from Ensembl.

    Parameters
    ----------
    gene_id : str
        Ensembl stable gene ID.

    Returns
    -------
    dict
        Gene metadata including description,
        coordinates, biotype, and strand.
    """

    url = (
        "https://rest.ensembl.org/lookup/id/"
        f"{gene_id}"
    )

    response = ensembl_get(url)
    data = response.json()

    return {
        "gene_id": data.get("id"),
        "gene_name": data.get("display_name") or "Unknown",
        "description": data.get("description") or "No description available.",
        "biotype": data.get("biotype"),
        "chromosome": data.get("seq_region_name"),
        "start": data.get("start"),
        "end": data.get("end"),
        "strand": data.get("strand"),
    }
