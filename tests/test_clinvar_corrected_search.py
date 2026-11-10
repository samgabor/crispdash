import time

from services.clinvar import search_clinvar_region


print("\nCORRECTED CLINVAR SEARCH TEST")
print("-" * 60)

# Test A: Known position with a ClinVar search match
print("\nTEST A: DPYD TEST POSITION")

result_a = search_clinvar_region(
    chrom="chr1",
    start=97079133,
    end=97079133
)

print(f"Search: {result_a['search_term']}")
print(f"Matches: {result_a['total_count']}")
print(f"IDs: {result_a['variant_ids'][:5]}")


# Respect NCBI rate limits

time.sleep(1)


# Test B: Our predicted off-target site
print("\nTEST B: SITE-002")

result_b = search_clinvar_region(
    chrom="chr1",
    start=97697293,
    end=97697315
)

print(f"Search: {result_b['search_term']}")
print(f"Matches: {result_b['total_count']}")
print(f"IDs: {result_b['variant_ids'][:5]}")