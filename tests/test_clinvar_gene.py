from services.clinvar import search_clinvar_gene


print("Testing ClinVar gene-level search...")

result = search_clinvar_gene("DPYD")

print("\nGene:", result["gene"])

print("Search term:", result["search_term"])

print("Total ClinVar records:", result["total_count"])

print("Retrieved variant IDs:", result["variant_ids"])

assert result["gene"] == "DPYD"

assert result["total_count"] > 0

assert len(result["variant_ids"]) > 0

assert len(result["variant_ids"]) <= 10

print("\nClinVar gene search test passed!")