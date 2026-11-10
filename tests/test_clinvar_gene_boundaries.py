from services.clinvar import annotate_clinvar_gene


# DPYD genomic boundaries from Ensembl (GRCh38)
GENE_CHROM = "1"
GENE_START = 97077743
GENE_END = 97995000

# SITE-002 coordinates
SITE_START = 97697293
SITE_END = 97697315


print("Testing ClinVar gene boundary verification...")

result = annotate_clinvar_gene(
    gene_symbol="DPYD",
    site_chrom=GENE_CHROM,
    site_start=SITE_START,
    site_end=SITE_END,
    max_records=5
)

for variant in result["gene_variants"]:

    within_gene = any(
        str(location["chromosome"]).removeprefix("chr")
        == GENE_CHROM
        and location["start"] <= GENE_END
        and location["end"] >= GENE_START
        for location in variant["locations"]
    )

    print("\nVariant:", variant["title"])
    print("Within DPYD boundaries:", within_gene)

    assert within_gene, (
        f"Variant outside DPYD boundaries: "
        f"{variant['title']}"
    )

print("\nGene boundary verification test passed!")