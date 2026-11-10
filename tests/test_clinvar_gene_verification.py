import time

from services.clinvar import (
    search_clinvar_gene_pathogenic,
    get_clinvar_variant_details,
    extract_grch38_locations,
    check_genomic_overlap
)


# SITE-002 coordinates (GRCh38)
SITE_CHROM = "1"
SITE_START = 97697293
SITE_END = 97697315


print("Verifying DPYD gene-level ClinVar variants...")

result = search_clinvar_gene_pathogenic(
    "DPYD",
    max_records=5
)

print("\nTotal search matches:", result["total_count"])

for variant_id in result["variant_ids"]:

    time.sleep(0.4)

    variant = get_clinvar_variant_details(variant_id)

    clinical = variant.get(
        "germline_classification", {}
    )

    significance = clinical.get(
        "description", "Not available"
    )

    locations = extract_grch38_locations(variant)

    overlaps_site = any(
        check_genomic_overlap(
            SITE_CHROM,
            SITE_START,
            SITE_END,
            location
        )
        for location in locations
    )

    print("\n-----------------------------")
    print("Variant ID:", variant_id)
    print("Variant:", variant.get("title"))
    print("Clinical significance:", significance)

    print("GRCh38 locations:")
    for location in locations:
        print(
            f"  chr{location['chromosome']}:"
            f"{location['start']}-{location['end']}"
        )

    print("Overlaps SITE-002:", overlaps_site)

print("\nGene-level verification test completed!")