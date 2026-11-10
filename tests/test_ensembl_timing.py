import time
from services.ensembl import ensembl_get

tests = {
    "Gene overlap": (
        "https://rest.ensembl.org/"
        "overlap/region/human/1:97697293-97697315",
        {"feature": "gene"}
    ),
    "Exon overlap": (
        "https://rest.ensembl.org/"
        "overlap/region/human/1:93138222-93138244",
        {"feature": "exon"}
    ),
    "DPYD gene information": (
        "https://rest.ensembl.org/"
        "lookup/id/ENSG00000188641",
        None
    )
}

for name, (url, params) in tests.items():
    print(f"\nTesting: {name}")

    start_time = time.perf_counter()

    try:
        response = ensembl_get(url, params=params)

        elapsed = time.perf_counter() - start_time

        print("Status:", response.status_code)
        print(f"Response time: {elapsed:.2f} seconds")

    except Exception as error:
        elapsed = time.perf_counter() - start_time

        print(f"Failed after {elapsed:.2f} seconds")
        print("Error:", error)