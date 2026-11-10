import pandas as pd
from pathlib import Path

from services.ensembl import get_overlapping_exons


# Locate dataset
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = PROJECT_ROOT / "data" / "offtarget_sites.csv"

df = pd.read_csv(DATA_FILE)

print("\nENSEMBL EXON ANNOTATION TEST")
print("-" * 60)

# Select one site annotated as exonic in the dataset
exonic_sites = df[df["regionType"] == "exon"]

if exonic_sites.empty:
    raise ValueError("No exonic sites found in the dataset.")

site = exonic_sites.iloc[0]

print(f"Site ID: {site['siteId']}")
print(f"Original annotation: {site['locusDesc']}")
print(
    f"Location: {site['chrom']}:"
    f"{site['start']}-{site['end']}"
)

# Query Ensembl
exons = get_overlapping_exons(
    chrom=site["chrom"],
    start=int(site["start"]),
    end=int(site["end"])
)

print(f"\nNumber of overlapping exon annotations: {len(exons)}")

if exons:
    print("\nFirst five exon annotations:")

    for exon in exons[:5]:
        print(exon)
else:
    print("\nNo overlapping exons found.")