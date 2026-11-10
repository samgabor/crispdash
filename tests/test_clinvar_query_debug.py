import time
import requests

NCBI_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

queries = [
    "DPYD[gene]",
    "1[Chromosome]",
    "97079133:97079133[Base Position]",
    "GRCh38[Assembly]",
    (
        "1[Chromosome] AND "
        "97079133:97079133[Base Position] AND "
        "GRCh38[Assembly]"
    ),
]

print("\nCLINVAR QUERY DIAGNOSTIC")
print("-" * 60)

for query in queries:

    print(f"\nOriginal query: {query}")

    # Wait between requests to respect NCBI rate limits
    time.sleep(1)

    for attempt in range(3):

        response = requests.get(
            NCBI_URL,
            params={
                "db": "clinvar",
                "term": query,
                "retmode": "json",
                "retmax": 3,
                "tool": "crispr_offtarget_dashboard",
            },
            timeout=20,
        )

        if response.status_code == 429:

            print("Rate limit reached. Waiting before retrying...")

            time.sleep(5 * (attempt + 1))

            continue

        response.raise_for_status()

        break

    else:
        raise RuntimeError(
            "NCBI rate limit persisted after three attempts."
        )

    response.raise_for_status()

    result = response.json()["esearchresult"]

    print(f"Matches: {result.get('count')}")
    print(f"Translation: {result.get('querytranslation')}")
    print(f"IDs: {result.get('idlist')}")

    if result.get("warninglist"):
        print(f"Warnings: {result['warninglist']}")

    if result.get("errorlist"):
        print(f"Errors: {result['errorlist']}")