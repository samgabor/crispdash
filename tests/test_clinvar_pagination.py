from services.clinvar import search_clinvar_region


print("\nCLINVAR PAGINATION TEST")
print("-" * 60)


# --------------------------------------------------
# TEST A: Known positive-control position
# --------------------------------------------------

print("\nTEST A: POSITIVE CONTROL")

result_a = search_clinvar_region(
    chrom="chr1",
    start=97079133,
    end=97079133
)

print(f"Total records: {result_a['total_count']}")
print(f"Retrieved IDs: {len(result_a['variant_ids'])}")
print(f"Truncated: {result_a['truncated']}")

assert "433" in result_a["variant_ids"]
assert result_a["truncated"] is False

print("Positive control passed!")


# --------------------------------------------------
# TEST B: Deliberately restrict retrieval
# --------------------------------------------------

print("\nTEST B: RETRIEVAL LIMIT")

result_b = search_clinvar_region(
    chrom="chr1",
    start=97079133,
    end=97079133,
    max_records=1
)

print(f"Total records: {result_b['total_count']}")
print(f"Retrieved IDs: {len(result_b['variant_ids'])}")
print(f"Truncated: {result_b['truncated']}")

assert len(result_b["variant_ids"]) <= 1

print("Retrieval limit test passed!")


print("\nAll pagination tests passed!")