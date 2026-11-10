import requests

# DPYD Ensembl gene identifier
gene_id = "ENSG00000188641"

url = f"https://rest.ensembl.org/lookup/id/{gene_id}"

response = requests.get(
    url,
    headers={"Accept": "application/json"},
    timeout=30
)

response.raise_for_status()

gene = response.json()

print("\n=== Ensembl Gene Summary Test ===")

print("Gene ID:", gene.get("id"))
print("Gene Symbol:", gene.get("display_name"))
print("Description:", gene.get("description"))
print("Biotype:", gene.get("biotype"))
print("Chromosome:", gene.get("seq_region_name"))
print("Start:", gene.get("start"))
print("End:", gene.get("end"))