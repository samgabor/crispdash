import json

from services.clinvar import get_clinvar_variant_details


print("\nCLINVAR VARIANT DETAILS TEST")
print("-" * 60)

# Positive-control ClinVar record
variant_id = "433"

variant = get_clinvar_variant_details(variant_id)

print(f"\nClinVar Variation ID: {variant_id}")

print("\nAvailable fields:")
for key in variant.keys():
    print(f"  {key}")

print("\nVARIATION SET:")
print(
    json.dumps(
        variant.get("variation_set", []),
        indent=2
    )
)

print("\nClinical significance:")
print(
    json.dumps(
        variant.get("germline_classification", {}),
        indent=2
    )
)