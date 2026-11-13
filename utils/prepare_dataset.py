from pathlib import Path
import pandas as pd

# --------------------------------------------------
# File paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "41591_2019_401_MOESM3_ESM.xlsx"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "offtarget_sites.csv"
)

# --------------------------------------------------
# Load original dataset
# --------------------------------------------------

df = pd.read_excel(
    SOURCE_FILE,
    sheet_name="Supplementary Table 5",
    header=11
)

# Clean column names
df.columns = df.columns.astype(str).str.strip()

# --------------------------------------------------
# Select the relevant guide
# --------------------------------------------------

df = df[df["guideId"] == "21forw"].copy()

# --------------------------------------------------
# Preserve original off-target identifiers
# --------------------------------------------------

df = df.rename(
    columns={
        "candidates for deep sequencing": "originalOTId"
    }
)

# Create a unique ID for every predicted site.
# These are dashboard IDs, not identifiers from the paper.
df.insert(
    0,
    "siteId",
    [f"SITE-{i:03d}" for i in range(1, len(df) + 1)]
)

# --------------------------------------------------
# Standardize genomic region categories
# --------------------------------------------------

df["regionType"] = (
    df["locusDesc"]
    .astype(str)
    .str.split(":")
    .str[0]
    .str.lower()
    .str.strip()
)

# --------------------------------------------------
# Reorder columns
# --------------------------------------------------

columns = [
    "siteId",
    "originalOTId",
    "guideId",
    "guideSeq",
    "offtargetSeq",
    "mismatchPos",
    "mismatchCount",
    "mitOfftargetScore",
    "cfdOfftargetScore",
    "chrom",
    "start",
    "end",
    "strand",
    "regionType",
    "locusDesc",
]

df = df[columns]

# --------------------------------------------------
# Save processed dataset
# --------------------------------------------------

df.to_csv(
    OUTPUT_FILE,
    index=False
)

# --------------------------------------------------
# Display summary
# --------------------------------------------------

print("\nDATASET PREPARATION COMPLETE")
print("-" * 50)

print(f"Total sites exported: {len(df)}")
print(f"Output file: {OUTPUT_FILE}")

print("\nFirst five records:")
print(
    df[
        [
            "siteId",
            "originalOTId",
            "chrom",
            "start",
            "end",
            "regionType",
            "cfdOfftargetScore",
        ]
    ].head().to_string(index=False)
)