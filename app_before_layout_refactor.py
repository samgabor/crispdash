import streamlit as st
import pandas as pd
from pathlib import Path
from urllib.parse import quote
import plotly.express as px

from services.ensembl import (
    get_overlapping_genes,
    get_overlapping_exons,
    get_gene_information
)

from services.clinvar import (
    annotate_clinvar_region,
    annotate_clinvar_gene,
    get_ncbi_gene_summary
)

# --------------------------------------------------
# Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="CRISPR Off-Target Dashboard",
    page_icon="🧬",
    layout="wide"
)

# --------------------------------------------------
# Application title
# --------------------------------------------------

st.title("🧬 CRISPR Off-Target Annotation Dashboard")

# --------------------------------------------------
# Guide RNA selection
# --------------------------------------------------

st.subheader("Guide RNA Selection")

selected_guide = st.selectbox(
    "Select Guide RNA",
    options=["sgRNA-1617"],
    help=(
        "This version analyzes sgRNA-1617, "
        "which targets the BCL11A enhancer."
    )
)

st.caption(
    "Target: BCL11A enhancer | "
    "Genome assembly: GRCh38 (hg38)"
)

st.code(
    "CTAACAGTTGCTTTTATCACagg",
    language=None
)
st.caption(
    "Guide-target sequence with Protospacer Adjacent Motif (PAM), as recorded "
    "in the published off-target dataset."
)

st.markdown(
    """
    Explore computationally predicted off-target sites
    associated with **sgRNA-1617**, targeting the
    **BCL11A enhancer**.

    Data source: Wu et al. (2019), Supplementary Table 5.
    """
)

st.divider()

# --------------------------------------------------
# Load dataset
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

DATA_FILE = PROJECT_ROOT / "data" / "offtarget_sites.csv"

@st.cache_data(ttl=3600)
def get_cached_gene_information(gene_id):
    return get_gene_information(gene_id)


@st.cache_data(ttl=3600)
def get_cached_ncbi_gene_summary(gene_symbol):
    return get_ncbi_gene_summary(gene_symbol)


@st.cache_data
def load_data():
    return pd.read_csv(DATA_FILE)


@st.cache_data(ttl=3600)
def load_ensembl_exons(chrom, start, end):
    """
    Retrieve unique overlapping exon annotations.

    Cache results for one hour.
    """
    return get_overlapping_exons(chrom, start, end)

@st.cache_data(ttl=3600)
def load_clinvar_annotations(chrom, start, end):
    """
    Retrieve ClinVar annotations for a genomic region.

    Cache results for one hour to reduce API requests.
    """
    return annotate_clinvar_region(chrom, start, end)

@st.cache_data(ttl=3600)
def get_cached_clinvar_gene(
    gene_symbol,
    chrom,
    start,
    end,
    gene_chrom,
    gene_start,
    gene_end
):
    return annotate_clinvar_gene(
        gene_symbol=gene_symbol,
        site_chrom=chrom,
        site_start=start,
        site_end=end,
        gene_chrom=gene_chrom,
        gene_start=gene_start,
        gene_end=gene_end,
        max_records=5
    )


@st.cache_data(ttl=3600)
def load_ensembl_annotations(chrom, start, end):
    """
    Retrieve overlapping genes from Ensembl.

    Cache results for one hour to avoid
    unnecessary repeated API requests.
    """
    return get_overlapping_genes(chrom, start, end)


df = load_data()

# --------------------------------------------------
# Dataset overview
# --------------------------------------------------

st.header("Dataset Overview")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="Predicted Off-Target Sites",
        value=len(df)
    )

with col2:
    st.metric(
        label="Exonic Sites",
        value=(df["regionType"] == "exon").sum()
    )

with col3:
    st.metric(
        label="Maximum CFD Score",
        value=f"{df['cfdOfftargetScore'].max():.3f}"
    )

st.divider()

# --------------------------------------------------
# Display predicted sites
# --------------------------------------------------

st.header("Predicted Off-Target Sites")

display_columns = [
    "siteId",
    "chrom",
    "start",
    "end",
    "mismatchCount",
    "cfdOfftargetScore",
    "regionType"
]

st.subheader("Filter Predicted Off-Target Sites")

min_cfd = st.slider(
    "Minimum Cutting Frequency Determination (CFD) Off-Target Score",
    min_value=0.0,
    max_value=1.0,
    value=0.0,
    step=0.01,
    help=(
        "Show only predicted off-target sites with "
        "CFD scores at or above this threshold."
    )
)

region_filter = st.selectbox(
    "Genomic Region",
    options=[
        "All Regions",
        "Intergenic",
        "Intron",
        "Exon"
    ],
    help=(
        "Filter predicted off-target sites "
        "by their annotated genomic region."
    )
)

# First, filter by CFD score
filtered_df = df[
    df["cfdOfftargetScore"] >= min_cfd
].copy()

# Then, optionally filter by genomic region
if region_filter != "All Regions":

    filtered_df = filtered_df[
        filtered_df["regionType"].str.lower()
        == region_filter.lower()
    ].copy()

st.caption(
    f"Showing {len(filtered_df)} of {len(df)} "
    "predicted off-target sites."
)

st.dataframe(
    filtered_df,
    width="stretch",
    hide_index=True
)

# --------------------------------------------------
# CFD score distribution
# --------------------------------------------------

st.subheader("CFD Score Distribution")

st.caption(
    "Distribution of predicted off-target cleavage "
    "propensity scores for the currently filtered sites."
)

if not filtered_df.empty:

    fig = px.histogram(
        filtered_df,
        x="cfdOfftargetScore",
        nbins=20,
        labels={
            "cfdOfftargetScore": "CFD Off-Target Score"
        }
    )

    fig.update_layout(
        xaxis_title="CFD Off-Target Score",
        yaxis_title="Number of Off-Target Sites",
        bargap=0.05
    )

    fig.update_xaxes(
        range=[0, 1],
        tickmode="linear",
        tick0=0,
        dtick=0.1,
        tickformat=".1f"
    )

    st.plotly_chart(
        fig,
        width="stretch"
    )

else:

    st.info(
        "No sites match the selected filters. "
        "Adjust the CFD threshold or genomic region."
    )

# --------------------------------------------------
# Genomic region distribution
# --------------------------------------------------

st.subheader("Genomic Region Distribution")

st.caption(
    "Number of predicted off-target sites in each "
    "genomic-region category for the currently filtered data."
)

if not filtered_df.empty:

    region_counts = (
        filtered_df["regionType"]
        .value_counts()
        .rename_axis("Region")
        .reset_index(name="Site Count")
    )

    fig_region = px.bar(
        region_counts,
        x="Region",
        y="Site Count",
        text="Site Count",
        labels={
            "Region": "Genomic Region",
            "Site Count": "Number of Off-Target Sites"
        },
        category_orders={
            "Region": ["intergenic", "intron", "exon"]
        }
    )

    fig_region.update_traces(
        textposition="outside"
    )

    fig_region.update_layout(
        xaxis_title="Genomic Region",
        yaxis_title="Number of Off-Target Sites",
        showlegend=False
    )

    st.plotly_chart(
        fig_region,
        width="stretch"
    )

else:

    st.info(
        "No sites match the selected filters."
    )

st.divider()

# --------------------------------------------------
# Select an off-target site
# --------------------------------------------------

st.header("Select an Off-Target Site")

selected_site = st.selectbox(
    "Choose a predicted site:",
    options=df["siteId"].tolist()
)

# Retrieve selected record
site = df[df["siteId"] == selected_site].iloc[0]

# --------------------------------------------------
# Display selected site information
# --------------------------------------------------

# --------------------------------------------------
# Analyze button
# --------------------------------------------------

analyze_button = st.button(
    "🔬 Analyze Selected Site",
    type="primary"
)

# --------------------------------------------------
# Display analysis results
# --------------------------------------------------

if analyze_button:

    st.divider()

    st.header(f"Analysis Results: {selected_site}")

    st.success(
        f"Analysis completed for {selected_site}."
    )

    # Genomic location
    st.subheader("Genomic Location")

    col1, col2 = st.columns(2)

    chrom = str(site["chrom"])
    start = int(site["start"])
    end = int(site["end"])


    with col1:
        st.write("**Chromosome:**", site["chrom"])
        st.write("**Start:**", site["start"])
        st.write("**End:**", site["end"])
        st.write("**Strand:**", site["strand"])

    with col2:
        st.write("**Region Type:**", site["regionType"])
        st.write(
            "**Locus Description:**",
            site["locusDesc"]
        )

    # UCSC Genome Browser link for the selected off-target site

    ucsc_chrom = f"chr{str(chrom).removeprefix('chr')}"

    ucsc_position = f"{ucsc_chrom}:{start}-{end}"

    ucsc_url = (
        "https://genome.ucsc.edu/cgi-bin/hgTracks"
        f"?db=hg38&position={ucsc_position}"
    )

    st.link_button(
        "🌐 View Selected Site in UCSC Genome Browser",
        ucsc_url
    )

    # CRISPR prediction information
    st.subheader("CRISPR Prediction")

    col1, col2 = st.columns(2)

    with col1:
        st.write(
            "**Mismatch Count:**",
            site["mismatchCount"]
        )

        st.write(
            "**Guide Sequence:**",
            site["guideSeq"]
        )

        st.write(
            "**Off-Target Sequence:**",
            site["offtargetSeq"]
        )

    with col2:
        st.write(
            "**CFD Score:**",
            round(site["cfdOfftargetScore"], 4)
        )

        st.write(
            "**MIT Score:**",
            round(site["mitOfftargetScore"], 4)
        )

    st.divider()

    # --------------------------------------------------
    # Ensembl genomic annotations
    # --------------------------------------------------

    st.subheader("Ensembl Gene Annotations")

    with st.spinner("Retrieving annotations from Ensembl..."):

        try:
            genes = load_ensembl_annotations(
                chrom=site["chrom"],
                start=int(site["start"]),
                end=int(site["end"])
            )

            if genes:

                st.success(
                    f"Found {len(genes)} overlapping gene(s)."
                )

                gene_df = pd.DataFrame(genes)

                st.dataframe(
                    gene_df,
                    width="stretch",
                    hide_index=True
                )

            else:

                st.info(
                    "No overlapping genes were identified "
                    "by Ensembl for this genomic region."
                )

        except Exception as error:

            st.error(
                "Unable to retrieve Ensembl annotations."
            )

            st.caption(
                f"Technical details: {error}"
            )

    # ----------------------------------------
    # Gene Information and Biological Function
    # ----------------------------------------

    st.subheader("Gene Information and Biological Function")

    if not genes:

        st.info(
            "No overlapping genes were identified by Ensembl "
            "at this predicted off-target location."
        )

        st.caption(
            "Intergenic regions may contain regulatory elements. "
            "Use the UCSC Genome Browser to explore nearby genes "
            "and genomic annotations."
        )

    else:

        for gene in genes:

            gene_id = gene["gene_id"]

            # Retrieve detailed Ensembl information
            gene_info = get_cached_gene_information(gene_id)

            gene_symbol = gene_info["gene_name"]

            if gene_symbol.lower() == "unknown":
                display_name = (
                    f"Unnamed {gene_info['biotype']} "
                    f"({gene_info['gene_id']})"
                )
            else:
                display_name = gene_symbol

            st.markdown(f"### {display_name}")

            # Ensembl information
            st.markdown("**Ensembl Gene Information**")

            st.write("Gene ID:", gene_info["gene_id"])
            st.write("Description:", gene_info["description"])
            st.write("Biotype:", gene_info["biotype"])

            st.write(
                "Genomic Location:",
                f"chr{gene_info['chromosome']}:"
                f"{gene_info['start']:,}-"
                f"{gene_info['end']:,}"
            )

            strand = (
                "Forward (+)"
                if gene_info["strand"] == 1
                else "Reverse (-)"
            )

            st.write("Strand:", strand)

            # NCBI biological function
            st.markdown("**NCBI Gene — Biological Function**")

            if gene_symbol and gene_symbol.lower() != "unknown":

                ncbi_gene = get_cached_ncbi_gene_summary(
                    gene_symbol
                )

                if ncbi_gene:

                    st.write(
                        ncbi_gene["biological_summary"]
                    )

                else:

                    st.info(
                        "No matching NCBI Gene summary "
                        "was found for this gene."
                    )

            else:

                st.info(
                    "This gene does not have a recognized "
                    "gene symbol, so an NCBI Gene summary "
                    "cannot currently be matched reliably."
                )

            # Ensembl external link
            ensembl_url = (
                "https://www.ensembl.org/Homo_sapiens/"
                f"Gene/Summary?g={gene_id}"
            )

            st.link_button(
                "View Gene in Ensembl",
                ensembl_url
            )

            # ClinVar gene-specific search link
            if gene_symbol and gene_symbol.strip().lower() != "unknown":
                clinvar_search = f"{gene_symbol}[gene]"

                clinvar_url = (
                    "https://www.ncbi.nlm.nih.gov/clinvar/"
                    f"?term={quote(clinvar_search)}"
                )

                st.link_button(
                    f"View {gene_symbol} in ClinVar",
                    clinvar_url
                )


            st.divider()

    # ----------------------------------------
    # Gene-level ClinVar context
    # ----------------------------------------

    st.subheader("Gene-Level ClinVar Context")

    # Store gene-level ClinVar results for the evidence summary
    gene_clinvar_results = []

    if not genes:
        st.info(
            "No overlapping genes were identified, "
            "so gene-level ClinVar context is not available."
        )

    else:
        for gene in genes:

            #st.write("DEBUG - Gene dictionary:", gene)

            #gene_symbol = gene.get("external_name")
            gene_symbol = gene.get("gene_name")

            if (
                    not gene_symbol
                    or str(gene_symbol).strip().lower() == "unknown"
            ):
                st.info(
                    "This overlapping gene does not have a recognized "
                    "gene symbol in the current Ensembl annotation. "
                    "Gene-level ClinVar searching is unavailable "
                    "for this gene."
                )
                continue

            st.markdown(f"### {gene_symbol}")

            with st.spinner(
                    f"Retrieving ClinVar context for {gene_symbol}..."
            ):
                # gene_clinvar = get_cached_clinvar_gene(
                #     gene_symbol,
                #     str(selected_site["chrom"]),
                #     int(selected_site["start"]),
                #     int(selected_site["end"])
                # )
                gene_clinvar = get_cached_clinvar_gene(
                    gene_symbol,
                    chrom,
                    start,
                    end,
                    gene["chromosome"],
                    int(gene["start"]),
                    int(gene["end"])
                )
            gene_clinvar_results.append(gene_clinvar)

            st.write(
                "**ClinVar pathogenic/likely pathogenic "
                "search matches:**",
                gene_clinvar["search_count"]
            )

            st.write(
                "**Records individually examined:**",
                gene_clinvar["records_examined"]
            )

            st.write(
                "**Verified variants elsewhere in the gene:**",
                len(gene_clinvar["gene_variants"])
            )

            if gene_clinvar["gene_variants"]:

                for variant in gene_clinvar["gene_variants"]:
                    st.markdown(
                        f"**{variant['title']}**"
                    )

                    st.write(
                        "Clinical significance:",
                        variant["clinical_significance"]
                    )

                    st.write(
                        "Review status:",
                        variant["review_status"]
                    )

            else:
                st.info(
                    "No qualifying gene-level variants "
                    "were found in the examined sample."
                )

            st.caption(
                "These ClinVar records are associated with "
                "the overlapping gene but do not overlap "
                "the selected off-target site. "
                "They provide gene-level clinical context, "
                "not evidence that CRISPR editing at this "
                "site would cause a clinical effect."
            )




    # --------------------------------------------------
    # Ensembl exon annotations
    # --------------------------------------------------

    st.subheader("Ensembl Exon Annotations")

    with st.spinner("Retrieving exon annotations..."):

        try:
            exons = load_ensembl_exons(
                chrom=site["chrom"],
                start=int(site["start"]),
                end=int(site["end"])
            )

            if exons:

                st.success(
                    f"Found {len(exons)} unique overlapping exon(s)."
                )

                exon_df = pd.DataFrame(exons)

                st.dataframe(
                    exon_df,
                    width="stretch",
                    hide_index=True
                )

            else:

                st.info(
                    "No overlapping exons were identified "
                    "by Ensembl for this genomic region."
                )

        except Exception as error:

            st.error(
                "Unable to retrieve Ensembl exon annotations."
            )

            st.caption(
                f"Technical details: {error}"
            )

    # --------------------------------------------------
    # ClinVar annotations
    # --------------------------------------------------

    st.subheader("ClinVar Variant Annotations")

    with st.spinner("Retrieving ClinVar annotations..."):

        try:
            clinvar_result = load_clinvar_annotations(
                chrom=site["chrom"],
                start=int(site["start"]),
                end=int(site["end"])
            )

            variants = clinvar_result["verified_variants"]

            st.caption(
                f"Candidate ClinVar records retrieved: "
                f"{clinvar_result['search_count']}"
            )

            if clinvar_result["truncated"]:
                st.warning(
                    "The ClinVar search returned more records "
                    "than the current retrieval limit. "
                    "Results may be incomplete."
                )

            if variants:

                st.success(
                    f"Found {len(variants)} verified "
                    f"ClinVar genomic overlap(s)."
                )

                clinvar_rows = []

                for variant in variants:

                    for location in variant["locations"]:

                        clinvar_rows.append({
                            "ClinVar ID": variant["clinvar_id"],
                            "Variant": variant["variant_name"],
                            "Chromosome": location["chromosome"],
                            "Start": location["start"],
                            "End": location["end"],
                            "Clinical significance": (
                                variant["clinical_significance"]
                            ),
                            "Review status": (
                                variant["review_status"]
                            ),
                            "Associated conditions": (
                                variant["conditions"]
                            ),
                        })

                clinvar_df = pd.DataFrame(clinvar_rows)

                st.dataframe(
                    clinvar_df,
                    width="stretch",
                    hide_index=True
                )

            else:

                st.info(
                    "No verified ClinVar overlaps were identified "
                    "among the records returned by the current "
                    "genomic-coordinate search."
                )

        except Exception as error:

            st.error(
                "Unable to retrieve ClinVar annotations."
            )

            st.caption(
                f"Technical details: {error}"
            )

    # ----------------------------------------
    # Integrated Evidence Summary
    # ----------------------------------------

    st.divider()

    st.header("Integrated Evidence Summary")

    st.markdown(
        "This summary combines computational off-target "
        "predictions with genomic annotation evidence."
    )

    # Prepare Ensembl findings for the evidence summary

    if genes:
        overlapping_gene_names = [
            gene["gene_name"]
            for gene in genes
            if gene.get("gene_name")
        ]

        gene_summary = (
            ", ".join(overlapping_gene_names)
            if overlapping_gene_names
            else "No named overlapping genes identified"
        )
    else:
        gene_summary = "No overlapping genes identified"

    exon_summary = str(len(exons))

    # ----------------------------------------
    # Prepare ClinVar evidence summary
    # ----------------------------------------

    # Direct ClinVar results
    direct_clinvar_count = len(
        clinvar_result["verified_variants"]
    )

    # Gene-level ClinVar results
    gene_clinvar_matches = "Not applicable"
    gene_clinvar_examined = "Not applicable"
    gene_clinvar_verified = "Not applicable"

    if gene_clinvar_results:
        gene_clinvar_matches = sum(
            result["search_count"]
            for result in gene_clinvar_results
        )

        gene_clinvar_examined = sum(
            result["records_examined"]
            for result in gene_clinvar_results
        )

        gene_clinvar_verified = sum(
            len(result["gene_variants"])
            for result in gene_clinvar_results
        )

    summary_data = {
        "Evidence Category": [
            "Selected Off-Target Site",
            "Genomic Coordinates (GRCh38)",
            "CFD Off-Target Score",
            "Sequence Mismatches",
            "Genomic Region",
            "Overlapping Genes (Ensembl)",
            "Overlapping Exons (Ensembl)",
            "Direct ClinVar Variant Overlaps",
            "Gene-Level ClinVar Search Matches",
            "Gene-Level Records Examined",
            "Verified Variants Elsewhere in Gene"
        ],
        "Finding": [
            selected_site,
            f"chr{str(chrom).removeprefix('chr')}:{start:,}-{end:,}",
            f"{float(site['cfdOfftargetScore']):.3f}",
            int(site["mismatchCount"]),
            site["regionType"],
            gene_summary,
            exon_summary,
            str(direct_clinvar_count),
            str(gene_clinvar_matches),
            str(gene_clinvar_examined),
            str(gene_clinvar_verified)
        ]
    }

    summary_df = pd.DataFrame(summary_data)

    # Ensure all findings are strings for Streamlit compatibility
    summary_df["Finding"] = summary_df["Finding"].astype(str)

    # st.dataframe(
    #     summary_df,
    #     hide_index=True,
    #     width="stretch",
    #     height = 460
    # )

    st.table(summary_df.set_index("Evidence Category"))

    # ----------------------------------------
    # Evidence Interpretation
    # ----------------------------------------

    st.subheader("Evidence Interpretation")

    if not genes:

        st.info(
            "Genomic context: This predicted off-target site "
            "does not overlap any genes identified by the "
            "current Ensembl query. This does not establish "
            "that editing at this location would be harmless."
        )

    elif len(exons) == 0:

        st.info(
            f"Genomic context: This predicted off-target site "
            f"overlaps the following gene(s): {gene_summary}. "
            "No overlapping exons were identified by Ensembl. "
            "This does not rule out functional effects from "
            "editing within the gene."
        )

    else:

        st.warning(
            f"Genomic context: This predicted off-target site "
            f"overlaps the following gene(s): {gene_summary}. "
            f"Ensembl identified {len(exons)} overlapping exon(s). "
            "Exon overlap may warrant closer investigation, "
            "but it does not establish that editing occurred "
            "or that a clinically harmful effect would result."
        )

    # ----------------------------------------
    # ClinVar Evidence Interpretation
    # ----------------------------------------

    st.markdown("#### Clinical Annotation Interpretation")

    # Direct ClinVar evidence
    if direct_clinvar_count > 0:

        st.warning(
            f"Direct ClinVar evidence: {direct_clinvar_count} "
            "ClinVar variant(s) were verified as overlapping "
            "the selected off-target coordinates (GRCh38). "
            "These are existing clinical variant annotations, "
            "not evidence that CRISPR editing occurred."
        )

    else:

        st.info(
            "Direct ClinVar evidence: No ClinVar variants "
            "were verified as overlapping the selected "
            "off-target coordinates in the current search. "
            "This does not establish that editing at this "
            "location would be safe."
        )

    # Gene-level ClinVar context
    if not gene_clinvar_results:

        st.info(
            "Gene-level clinical context: No overlapping "
            "gene with retrieved ClinVar annotations was "
            "available for this site."
        )

    else:

        if gene_clinvar_verified > 0:

            st.info(
                "Gene-level clinical context: ClinVar returned "
                f"{gene_clinvar_matches} pathogenic/likely "
                "pathogenic search matches across the overlapping "
                "gene(s). "
                f"We individually examined {gene_clinvar_examined} "
                "record(s) and verified "
                f"{gene_clinvar_verified} pathogenic/likely "
                "pathogenic variant(s) elsewhere within the "
                "overlapping gene(s). "
                "These variants provide gene-level clinical "
                "context but do not establish the consequences "
                "of editing at the selected off-target site."
            )

        else:

            st.info(
                "Gene-level clinical context: ClinVar returned "
                f"{gene_clinvar_matches} pathogenic/likely "
                "pathogenic search matches across the overlapping "
                "gene(s). "
                f"We individually examined {gene_clinvar_examined} "
                "record(s), but none met our verification criteria "
                "for pathogenic/likely pathogenic variants "
                "elsewhere within the overlapping gene(s). "
                "This does not mean that no clinically significant "
                "variants exist in these genes, because only a "
                "limited sample of records was examined."
            )

    st.caption(
        "CFD scores estimate relative sequence-based "
        "off-target potential. They do not represent "
        "the probability of a clinically harmful edit."
    )



    st.caption(
        "ClinVar reports clinical interpretations of "
        "specific genetic variants. A genomic overlap "
        "does not establish that CRISPR editing occurred "
        "or that an off-target edit would have the same "
        "clinical consequences as the reported variant."
    )

