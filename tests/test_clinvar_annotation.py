import time

from services.clinvar import annotate_clinvar_region


print("\nCLINVAR ANNOTATION PIPELINE TEST")
print("-" * 60)


# --------------------------------------------------
# TEST A: Known ClinVar variant position
# --------------------------------------------------

print("\nTEST A: POSITIVE CONTROL")

result_a = annotate_clinvar_region(
    chrom="chr1",
    start=97079133,
    end=97079133
)

print(f"Candidate records: {result_a['search_count']}")
print(
    f"Verified overlaps: "
    f"{len(result_a['verified_variants'])}"
)

for variant in result_a["verified_variants"]:

    print(f"\nClinVar ID: {variant['clinvar_id']}")
    print(f"Variant: {variant['variant_name']}")
    print(
        f"Clinical significance: "
        f"{variant['clinical_significance']}"
    )
    print(f"Review status: {variant['review_status']}")
    print(f"Conditions: {variant['conditions']}")

assert any(
    variant["clinvar_id"] == "433"
    for variant in result_a["verified_variants"]
)

print("\nPositive control passed!")


# Respect NCBI request limits
time.sleep(1)


# --------------------------------------------------
# TEST B: SITE-002
# --------------------------------------------------

print("\nTEST B: SITE-002")

result_b = annotate_clinvar_region(
    chrom="chr1",
    start=97697293,
    end=97697315
)

print(f"Candidate records: {result_b['search_count']}")
print(
    f"Verified overlaps: "
    f"{len(result_b['verified_variants'])}"
)

print(f"Search truncated: {result_b['truncated']}")

print("\nClinVar annotation pipeline test completed!")