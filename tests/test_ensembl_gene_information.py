from services.ensembl import get_gene_information


def test_gene(gene_id):

    print("\n" + "=" * 60)
    print("Testing Ensembl Gene:", gene_id)

    gene = get_gene_information(gene_id)

    print("Gene ID:", gene["gene_id"])
    print("Gene Name:", gene["gene_name"])
    print("Description:", gene["description"])
    print("Biotype:", gene["biotype"])
    print("Chromosome:", gene["chromosome"])
    print("Start:", gene["start"])
    print("End:", gene["end"])
    print("Strand:", gene["strand"])


# Protein-coding gene (SITE-002)
test_gene("ENSG00000188641")

# Unnamed lncRNA (SITE-005)
test_gene("ENSG00000297478")