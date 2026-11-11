"""Load the curated multi-guide CRISPOR seed file."""
from pathlib import Path

import pandas as pd


def load_selected_offtargets(path: Path):
    data = pd.read_csv(path, encoding="utf-8-sig")
    data.columns = data.columns.str.strip()
    data = data.rename(columns={"siteid": "siteId", "region": "regionType"})
    metadata = ["name", "genome", "disease", "target", "position", "guideSeq", "crispor"]
    required = metadata + ["siteId", "guideId", "offtargetSeq", "mismatchPos",
                           "mismatchCount", "mitOfftargetScore", "cfdOfftargetScore",
                           "chrom", "start", "end", "strand", "regionType", "locusDesc"]
    missing = set(required) - set(data.columns)
    if missing:
        raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
    if data.empty:
        raise ValueError("The selected off-target CSV has no rows.")
    if data[required].isna().any().any():
        raise ValueError("The selected off-target CSV contains missing required values.")
    for column in metadata + ["siteId", "chrom", "regionType"]:
        data[column] = data[column].astype(str).str.strip()
        if data[column].eq("").any():
            raise ValueError(f"The CSV contains an empty {column} value.")
    if not data["genome"].str.lower().eq("hg38").all():
        raise ValueError("Live Ensembl and ClinVar annotations currently require hg38 guides.")
    if data.duplicated(["name", "siteId"]).any():
        raise ValueError("Site IDs must be unique within each guide.")
    for name, group in data.groupby("name", sort=False):
        if any(group[column].nunique() != 1 for column in metadata):
            raise ValueError(f"Conflicting guide metadata for {name}.")
    data["regionType"] = data["regionType"].str.lower()
    return data
