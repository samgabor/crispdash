from services.clinvar import search_clinvar_region


print("\nCLINVAR GENOMIC REGION TEST")
print("-" * 60)

# SITE-002: DPYD-associated off-target site
result = search_clinvar_region(
    chrom="chr1",
    start=97697293,
    end=97697315
)

print(f"\nSearch term: {result['search_term']}")
print(f"Total matching records: {result['total_count']}")
print(f"ClinVar IDs: {result['variant_ids'][:10]}")