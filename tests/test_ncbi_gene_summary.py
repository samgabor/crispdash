import requests

# NCBI Gene ID for DPYD
gene_id = "1806"

url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

params = {
    "db": "gene",
    "id": gene_id,
    "retmode": "json"
}

response = requests.get(
    url,
    params=params,
    timeout=30
)

response.raise_for_status()

data = response.json()

gene = data["result"][gene_id]

print("\n=== NCBI Gene Summary ===")

print("Gene Symbol:", gene.get("name"))
print("Full Name:", gene.get("description"))
print("\nBiological Summary:")
print(gene.get("summary"))