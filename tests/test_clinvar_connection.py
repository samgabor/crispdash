import requests

# NCBI E-utilities endpoint
NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

url = f"{NCBI_BASE_URL}/esearch.fcgi"

# Search ClinVar for variants associated with DPYD
params = {
    "db": "clinvar",
    "term": "DPYD[gene]",
    "retmode": "json",
    "retmax": 5,
    "tool": "crispr_offtarget_dashboard",
    "email": "sg662@columbia.edu",
}

print("\nNCBI CLINVAR CONNECTION TEST")
print("-" * 60)

try:
    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    result = response.json()

    search_results = result["esearchresult"]

    print("Connection successful!")
    print(f"Total matching records: {search_results['count']}")
    print(f"First five ClinVar IDs: {search_results['idlist']}")

except requests.RequestException as error:
    print(f"Connection failed: {error}")

except (KeyError, ValueError) as error:
    print(f"Unexpected API response: {error}")