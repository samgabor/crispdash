from services.clinvar import search_clinvar_gene_pathogenic


print("Testing pathogenic ClinVar gene search...")

result = search_clinvar_gene_pathogenic(
    "DPYD",
    max_records=10
)

print("\nGene:", result["gene"])
print("Search term:", result["search_term"])
print("Total matching records:", result["total_count"])
print("Retrieved variant IDs:", result["variant_ids"])

assert result["gene"] == "DPYD"
assert result["total_count"] > 0
assert len(result["variant_ids"]) > 0
assert len(result["variant_ids"]) <= 10

print("\nPathogenic ClinVar gene search test passed!")