from services.clinvar import (
    search_clinvar_gene,
    get_clinvar_variant_details
)

import time


print("Testing ClinVar gene-level variant details...")

# Search for DPYD-associated variants
search_result = search_clinvar_gene(
    "DPYD",
    max_records=5
)

variant_ids = search_result["variant_ids"]

print("\nGene:", search_result["gene"])
print("Total ClinVar records:", search_result["total_count"])
print("Retrieving details for:", len(variant_ids), "variants")

for variant_id in variant_ids:

    # Respect NCBI request-rate limits
    time.sleep(0.4)

    variant = get_clinvar_variant_details(variant_id)

    print("\n-----------------------------")
    print("Variant ID:", variant_id)

    print(
        "Variant name:",
        variant.get("title", "Not available")
    )

    clinical = variant.get(
        "germline_classification", {}
    )

    print(
        "Clinical significance:",
        clinical.get(
            "description",
            "Not available"
        )
    )

    print(
        "Review status:",
        clinical.get(
            "review_status",
            "Not available"
        )
    )

print("\nGene-level variant details test passed!")