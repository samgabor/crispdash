from pathlib import Path
import pandas as pd

# Locate the Excel workbook
PROJECT_ROOT = Path(__file__).resolve().parent

EXCEL_FILE = (
    PROJECT_ROOT
    / "data"
    / "41591_2019_401_MOESM3_ESM.xlsx"
)

# Load Supplementary Table 5
# Excel row 12 contains the headers.
# pandas uses zero-based indexing, so header=11.
df = pd.read_excel(
    EXCEL_FILE,
    sheet_name="Supplementary Table 5",
    header=11
)

# Remove leading/trailing spaces from column names
df.columns = df.columns.astype(str).str.strip()

print("\nCOLUMN NAMES")
print("-" * 60)
print(df.columns.tolist())

print("\nTOTAL ROWS")
print("-" * 60)
print(len(df))

print("\nGUIDE IDs")
print("-" * 60)
print(df["guideId"].dropna().unique())

print("\nFIRST 10 RECORDS")
print("-" * 60)
print(df.head(10).to_string(index=False))

print("\nMISSING VALUES")
print("-" * 60)
print(df.isnull().sum())

print("\nDATA VALIDATION")
print("-" * 60)

# Check for missing values in essential columns
required_columns = [
    "guideId",
    "guideSeq",
    "offtargetSeq",
    "mismatchCount",
    "cfdOfftargetScore",
    "chrom",
    "start",
    "end",
    "strand",
]

missing_required = df[required_columns].isnull().sum()

print("\nMissing required values:")
print(missing_required)

# Check genomic coordinates
invalid_coordinates = df[
    (df["start"] <= 0)
    | (df["end"] < df["start"])
]

print("\nInvalid genomic coordinates:")
print(len(invalid_coordinates))

# Check CFD scores
invalid_cfd = df[
    (df["cfdOfftargetScore"] < 0)
    | (df["cfdOfftargetScore"] > 1)
]

print("\nCFD scores outside 0–1:")
print(len(invalid_cfd))

# Check duplicate genomic locations
duplicates = df.duplicated(
    subset=["chrom", "start", "end", "strand"]
)

print("\nDuplicate genomic locations:")
print(duplicates.sum())

# Examine mismatch counts
print("\nMismatch count distribution:")
print(
    df["mismatchCount"]
    .value_counts()
    .sort_index()
)

# Examine genomic region descriptions
print("\nGenomic region categories:")
print(
    df["locusDesc"]
    .astype(str)
    .str.split(":")
    .str[0]
    .value_counts()
)

# Examine score distribution
print("\nCFD score summary:")
print(df["cfdOfftargetScore"].describe())

print("\nCOORDINATE LENGTH VALIDATION")
print("-" * 60)

# Length of each off-target DNA sequence
df["sequenceLength"] = df["offtargetSeq"].str.len()

# Interval length assuming 1-based inclusive coordinates
df["inclusiveLength"] = df["end"] - df["start"] + 1

# Interval length assuming 0-based half-open coordinates
df["halfOpenLength"] = df["end"] - df["start"]

# Count matches under each convention
inclusive_matches = (
    df["sequenceLength"] == df["inclusiveLength"]
).sum()

half_open_matches = (
    df["sequenceLength"] == df["halfOpenLength"]
).sum()

print(f"Total records: {len(df)}")
print(f"Matches using 1-based inclusive: {inclusive_matches}")
print(f"Matches using 0-based half-open: {half_open_matches}")

print("\nFirst five records:")
print(
    df[
        [
            "chrom",
            "start",
            "end",
            "sequenceLength",
            "inclusiveLength",
            "halfOpenLength",
        ]
    ].head().to_string(index=False)
)

# from pathlib import Path
# import pandas as pd
#
# # Locate the Excel workbook
# PROJECT_ROOT = Path(__file__).resolve().parent
#
# EXCEL_FILE = (
#     PROJECT_ROOT
#     / "data"
#     / "41591_2019_401_MOESM3_ESM.xlsx"
# )
#
# # Verify the file exists
# if not EXCEL_FILE.exists():
#     raise FileNotFoundError(
#         f"Excel workbook not found: {EXCEL_FILE}"
#     )
#
# # Open the workbook
# workbook = pd.ExcelFile(EXCEL_FILE)
#
# # Display worksheet names
# print("\nWORKSHEETS")
# print("-" * 50)
#
# for sheet in workbook.sheet_names:
#     print(sheet)
#
# # Inspect each worksheet
# for sheet_name in workbook.sheet_names:
#
#     print(f"\nWORKSHEET: {sheet_name}")
#     print("-" * 50)
#
#     # Read without assuming which row contains headers
#     df = pd.read_excel(
#         EXCEL_FILE,
#         sheet_name=sheet_name,
#         header=None,
#         nrows=12
#     )
#
#     print(df.to_string(index=False, header=False))
#