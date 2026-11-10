from services.clinvar import get_ncbi_gene_summary


print("\n=== NCBI Gene Function Test ===")

gene = get_ncbi_gene_summary("DPYD")

if gene:

    print("NCBI Gene ID:", gene["gene_id"])
    print("Gene Symbol:", gene["gene_symbol"])
    print("Full Name:", gene["full_name"])

    print("\nBiological Function:")
    print(gene["biological_summary"])

else:

    print("No matching NCBI Gene record found.")