from services.clinvar import search_clinvar_region


print("\nCLINVAR SEARCH VALIDATION")
print("-" * 60)

# --------------------------------------------------
# Test A: Predicted off-target location
# --------------------------------------------------

print("\nTEST A: SITE-002")

result_a = search_clinvar_region(
    chrom="chr1",
    start=97697293,
    end=97697315
)

print(f"Search: {result_a['search_term']}")
print(f"Matches: {result_a['total_count']}")
print(f"IDs: {result_a['variant_ids'][:5]}")


# --------------------------------------------------
# Test B: Previously identified DPYD variant position
# --------------------------------------------------

print("\nTEST B: DPYD VARIANT POSITION")

result_b = search_clinvar_region(
    chrom="chr1",
    start=97079133,
    end=97079133
)

print(f"Search: {result_b['search_term']}")
print(f"Matches: {result_b['total_count']}")
print(f"IDs: {result_b['variant_ids'][:5]}")