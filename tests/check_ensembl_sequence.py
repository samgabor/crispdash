import requests
import pandas as pd
from pathlib import Path

# --------------------------------------------------
# Load the dataset
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = PROJECT_ROOT / "data" / "offtarget_sites.csv"

df = pd.read_csv(DATA_FILE)

# Select SITE-002
site = df[df["siteId"] == "SITE-002"].iloc[0]

chrom = site["chrom"].replace("chr", "")
start = int(site["start"])
end = int(site["end"])
strand = site["strand"]

expected_sequence = site["offtargetSeq"].upper()

# --------------------------------------------------
# Request reference sequence from Ensembl
# --------------------------------------------------

strand_value = 1 if strand == "+" else -1

region = f"{chrom}:{start}..{end}:{strand_value}"

url = f"https://rest.ensembl.org/sequence/region/human/{region}"

print("\nENSEMBL SEQUENCE VERIFICATION")
print("-" * 60)

print(f"Site: {site['siteId']}")
print(f"Region: {region}")
print("Assembly: GRCh38")

try:
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        timeout=20
    )

    response.raise_for_status()

    result = response.json()

    reference_sequence = result["seq"].upper()

    print(f"\nDataset sequence: {expected_sequence}")
    print(f"Ensembl sequence: {reference_sequence}")

    if expected_sequence == reference_sequence:
        print("\nRESULT: EXACT MATCH")
        print("The coordinates and strand match the GRCh38 reference.")
    else:
        print("\nRESULT: SEQUENCES DO NOT MATCH")
        print("Further investigation is required.")

except requests.RequestException as error:
    print(f"\nAPI request failed: {error}")