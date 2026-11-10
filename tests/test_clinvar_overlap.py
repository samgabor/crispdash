from services.clinvar import (
    get_clinvar_variant_details,
    extract_grch38_locations,
    check_genomic_overlap,
)


print("\nCLINVAR GENOMIC OVERLAP TEST")
print("-" * 60)

# Retrieve our positive-control ClinVar variant
variant = get_clinvar_variant_details("433")

locations = extract_grch38_locations(variant)

if not locations:
    raise ValueError(
        "No GRCh38 locations found for ClinVar ID 433."
    )

location = locations[0]


# --------------------------------------------------
# TEST A: Positive overlap
# --------------------------------------------------

print("\nTEST A: POSITIVE CONTROL")

overlap_a = check_genomic_overlap(
    site_chrom="chr1",
    site_start=97079133,
    site_end=97079133,
    variant_location=location
)

print(f"Overlap detected: {overlap_a}")

assert overlap_a is True


# --------------------------------------------------
# TEST B: SITE-002
# --------------------------------------------------

print("\nTEST B: SITE-002")

overlap_b = check_genomic_overlap(
    site_chrom="chr1",
    site_start=97697293,
    site_end=97697315,
    variant_location=location
)

print(f"Overlap detected: {overlap_b}")

assert overlap_b is False


# --------------------------------------------------
# TEST C: Different chromosome
# --------------------------------------------------

print("\nTEST C: DIFFERENT CHROMOSOME")

overlap_c = check_genomic_overlap(
    site_chrom="chr2",
    site_start=97079133,
    site_end=97079133,
    variant_location=location
)

print(f"Overlap detected: {overlap_c}")

assert overlap_c is False


print("\nAll genomic overlap tests passed!")