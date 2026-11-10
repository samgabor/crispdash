from services.clinvar import (
    get_clinvar_variant_details,
    extract_grch38_locations,
)


print("\nCLINVAR GRCh38 EXTRACTION TEST")
print("-" * 60)

# Our validated positive-control record
variant = get_clinvar_variant_details("433")

locations = extract_grch38_locations(variant)

print(f"\nClinVar Variation ID: {variant['uid']}")
print(f"GRCh38 locations found: {len(locations)}")

for location in locations:
    print(f"\nChromosome: {location['chromosome']}")
    print(f"Start: {location['start']}")
    print(f"End: {location['end']}")
    print(f"Assembly: {location['assembly']}")
    print(f"Variant: {location['variation_name']}")
    print(f"Variant type: {location['variant_type']}")