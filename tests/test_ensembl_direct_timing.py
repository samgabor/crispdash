import time
import requests

from services.ensembl import ensembl_get

url = (
    "https://rest.ensembl.org/"
    "lookup/id/ENSG00000188641"
)

print("\n=== Direct Requests Test ===")

start = time.perf_counter()

response = requests.get(
    url,
    headers={"Accept": "application/json"},
    timeout=30
)

elapsed = time.perf_counter() - start

print("Status:", response.status_code)
print(f"Direct request time: {elapsed:.2f} seconds")


print("\n=== Existing Ensembl Helper Test ===")

start = time.perf_counter()

response = ensembl_get(url)

elapsed = time.perf_counter() - start

print("Status:", response.status_code)
print(f"Helper request time: {elapsed:.2f} seconds")