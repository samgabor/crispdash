from services.ensembl import get_overlapping_genes


print("\nENSEMBL GENE ANNOTATION TEST")
print("-" * 60)

# SITE-002: DPYD-associated off-target
genes = get_overlapping_genes(
    chrom="chr1",
    start=97697293,
    end=97697315
)

print(f"\nNumber of overlapping genes: {len(genes)}")

if genes:
    for gene in genes:
        print("\nGene annotation:")
        print(f"Gene ID: {gene['gene_id']}")
        print(f"Gene Name: {gene['gene_name']}")
        print(f"Biotype: {gene['biotype']}")
        print(f"Chromosome: {gene['chromosome']}")
        print(f"Start: {gene['start']}")
        print(f"End: {gene['end']}")
        print(f"Strand: {gene['strand']}")
else:
    print("\nNo overlapping genes found.")