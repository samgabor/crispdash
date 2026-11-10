from services.clinvar import annotate_clinvar_gene


print("Testing ClinVar gene-level annotation...")

result = annotate_clinvar_gene(
    gene_symbol="DPYD",
    site_chrom="1",
    site_start=97697293,
    site_end=97697315,
    max_records=5
)

print("\nGene:", result["gene"])
print("Total search matches:", result["search_count"])
print("Records examined:", result["records_examined"])

print(
    "Verified variants elsewhere:",
    len(result["gene_variants"])
)

print(
    "Direct overlaps:",
    len(result["direct_overlaps"])
)

print(
    "Excluded records:",
    result["excluded_count"]
)

for variant in result["gene_variants"]:

    print("\n-----------------------------")
    print("Variant:", variant["title"])
    print(
        "Clinical significance:",
        variant["clinical_significance"]
    )

assert result["gene"] == "DPYD"
assert result["records_examined"] == 5

assert all(
    variant["clinical_significance"].lower()
    in {"pathogenic", "likely pathogenic"}
    for variant in result["gene_variants"]
)

assert len(result["gene_variants"]) + len(
    result["direct_overlaps"]
) + result["excluded_count"] == result["records_examined"]

print("\nGene-level annotation test passed!")