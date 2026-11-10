import streamlit as st
import pandas as pd
from pathlib import Path
from urllib.parse import quote
import plotly.express as px
from requests.exceptions import RequestException
from config import DEBUG

from services.annotations import (
    collect_annotations, annotation_value, IncompleteAnnotations
)

st.set_page_config(
    page_title="CRISPR Off-Target Dashboard", page_icon="🧬",
    layout="wide", initial_sidebar_state="expanded"
)

PROJECT_ROOT = Path(__file__).resolve().parent

DATA_FILE = PROJECT_ROOT / "data" / "offtarget_sites.csv"
EXPLORE_TAB = "Explore Sites"
ANALYSIS_TAB = "Site Analysis"

# Verified 2026-11-08: CRISPOR 5.2, sgRNA-1617 + AGG, human hg38.
# This current run is separate from the published CRISPOR 4.2 dataset.
CRISPOR_RESULTS_URL = (
    "https://crispor.gi.ucsc.edu/crispor.py?batchId=FGYD8q8PWlNr2psRec6K"
)

@st.cache_data
def load_data():
    return pd.read_csv(DATA_FILE)


@st.cache_data(ttl=3600)
def load_site_annotations(chrom, start, end):
    """Cache complete analyses; partial failures remain immediately retryable."""
    results = collect_annotations(chrom, start, end)
    if results["errors"]:
        raise IncompleteAnnotations(results)
    return results


def display_lookup_timing(annotations, key):
    """Show lookup duration and every individual HTTP attempt alongside results."""
    timing = annotations["timings"].get(key)
    if timing is None:
        return
    requests = timing["requests"]
    st.caption(
        f"Lookup time: {timing['elapsed_seconds']:.3f} s · "
        f"HTTP attempts: {len(requests)} (including retries)"
    )
    if DEBUG and requests:
        with st.expander("HTTP response times"):
            st.caption(
                "Response time runs from sending each request until its response body "
                "arrives, or the request fails. Lookup time also includes pacing, "
                "retry waits, and response processing."
            )
            rows = [{
                "Attempt": index,
                "Service": record["provider"],
                "Endpoint": record["endpoint"],
                "Query": record["query"],
                "Status": record["status"],
                "Response time (s)": round(record["elapsed_seconds"], 6),
            } for index, record in enumerate(requests, 1)]
            st.dataframe(
                pd.DataFrame(rows), hide_index=True, width="stretch",
                alt="Individual REST request response times for this lookup"
            )


df = load_data()

st.session_state.setdefault("analyzed_site", None)
# Normalize older tab labels from existing browser sessions.
st.session_state["main_tab"] = {
    EXPLORE_TAB.casefold(): EXPLORE_TAB,
    ANALYSIS_TAB.casefold(): ANALYSIS_TAB,
}.get(str(st.session_state.get("main_tab", EXPLORE_TAB)).casefold(), EXPLORE_TAB)


def select_table_site(site_ids):
    """Map the selected display row to its site before the widgets rerun."""
    cells = st.session_state["site_table"]["selection"]["cells"]
    if cells:
        st.session_state["selected_site"] = site_ids[cells[0][0]]
        st.session_state["main_tab"] = EXPLORE_TAB


def analyze_selected_site():
    st.session_state["analyzed_site"] = st.session_state["selected_site"]
    st.session_state["main_tab"] = ANALYSIS_TAB


with st.sidebar:
    st.header("Guide & Filters")
    selected_guide = st.selectbox(
        "Guide RNA", ["sgRNA-1617"], key="guide",
        accept_new_options=False, filter_mode=None,
        help="Targets the BCL11A enhancer."
    )
    st.caption("BCL11A enhancer · GRCh38 (hg38)")
    with st.expander("Guide sequence & source"):
        st.code("CTAACAGTTGCTTTTATCACagg", language=None)
        st.caption("Guide-target DNA with PAM, as recorded in the published dataset.")
        st.caption("Wu et al. (2019), Supplementary Table 5.")

    st.link_button(
        "Open sgRNA-1617 in CRISPOR",
        CRISPOR_RESULTS_URL,
        width="stretch",
        help="Verified hg38 / NGG results: 155 predicted sites in CRISPOR 5.2."
    )
    st.caption("Current CRISPOR results; this dashboard retains the 154 published sites.")

    min_cfd = st.slider(
        "Minimum CFD score", 0.0, 1.0, 0.0, 0.01, key="min_cfd",
        help="Show sites at or above this sequence-based off-target score."
    )
    region_filter = st.selectbox(
        "Source genomic region", ["All Regions", "Intergenic", "Intron", "Exon"],
        accept_new_options=False, filter_mode=None,
        key="region_filter", help="Region labels from the published dataset."
    )

filtered_df = df[df["cfdOfftargetScore"] >= min_cfd].copy()
if region_filter != "All Regions":
    filtered_df = filtered_df[
        filtered_df["regionType"].str.lower() == region_filter.lower()
    ].copy()

with st.sidebar:
    st.subheader("Site Analysis")
    # Site selection follows the same filters as the table and charts.
    site_options = filtered_df["siteId"].tolist()
    if st.session_state.get("selected_site") not in site_options:
        st.session_state["selected_site"] = site_options[0] if site_options else None
    selected_site = st.selectbox(
        "Predicted off-target site", site_options, key="selected_site",
        accept_new_options=False, filter_mode=None,
        disabled=not site_options, placeholder="No matching sites"
    )
    st.button(
        "Analyze Selected Site", icon=":material/biotech:", type="primary",
        width="stretch", disabled=not site_options, key="analyze",
        on_click=analyze_selected_site
    )
    st.caption(f"{len(filtered_df)} of {len(df)} sites match the filters.")

st.title("🧬 CRISPR Off-Target Dashboard")
st.caption("sgRNA-1617 · BCL11A enhancer · GRCh38 (hg38) · Computational predictions and genomic annotations")

metric_grid = st.grid(4, min_column_width=160)
for label, value in [
    ("Predicted sites", len(df)),
    ("Source exonic sites", int((df["regionType"] == "exon").sum())),
    ("Maximum CFD score", f"{df['cfdOfftargetScore'].max():.3f}"),
    ("Matching sites", len(filtered_df)),
]:
    metric_grid.metric(label, value, border=True)

explore_tab, analysis_tab = st.tabs(
    [EXPLORE_TAB, ANALYSIS_TAB],
    key="main_tab", on_change="rerun"
)

with explore_tab:
    table_column, chart_column = st.columns([3, 2], gap="large")
    with table_column:
        st.subheader("Predicted Off-Target Sites")
        st.caption("Click a table row or choose a site in the sidebar, then select Analyze selected site.")
        if filtered_df.empty:
            st.info("No sites match these filters. Lower the CFD threshold or choose another region.")
        else:
            st.dataframe(
                filtered_df, column_order=[
                    "siteId", "chrom", "start", "end", "mismatchCount",
                    "cfdOfftargetScore", "regionType"
                ], width="stretch", hide_index=True, height=365,
                key="site_table", selection_mode="single-cell",
                on_select=lambda: select_table_site(site_options),
                alt="Predicted off-target sites matching the sidebar filters"
            )
        st.caption("Region categories are source labels; live Ensembl overlaps are reported separately in the analysis.")

    with chart_column:
        if not filtered_df.empty:
            st.markdown("**CFD score distribution**")
            fig = px.histogram(
                filtered_df, x="cfdOfftargetScore", nbins=20,
                labels={"cfdOfftargetScore": "CFD score"}
            )
            fig.update_layout(
                height=190, margin=dict(l=10, r=10, t=10, b=30),
                yaxis_title="Sites", bargap=0.05
            )
            fig.update_xaxes(range=[0, 1], dtick=0.2, tickformat=".1f")
            st.plotly_chart(fig, width="stretch", alt="CFD scores of matching off-target sites")

            st.markdown("**Source genomic region distribution**")
            region_counts = (filtered_df["regionType"].value_counts()
                             .rename_axis("Region").reset_index(name="Sites"))
            fig_region = px.bar(
                region_counts, x="Region", y="Sites", text="Sites",
                category_orders={"Region": ["intergenic", "intron", "exon"]}
            )
            fig_region.update_traces(textposition="outside", cliponaxis=False)
            fig_region.update_layout(
                height=190, margin=dict(l=10, r=10, t=20, b=30),
                showlegend=False, xaxis_title=None
            )
            st.plotly_chart(fig_region, width="stretch", alt="Matching sites by source genomic region")
        else:
            st.caption("Charts will appear when sites match the filters.")

with analysis_tab:
    if st.session_state["analyzed_site"] != selected_site or selected_site is None:
        st.info("Choose a matching site in the sidebar and select Analyze selected site to view its annotations.")
    else:
        site = df[df["siteId"] == selected_site].iloc[0]
        chrom, start, end = str(site["chrom"]), int(site["start"]), int(site["end"])
        st.subheader(f"Analysis: {selected_site}")
        st.caption(
            f"chr{chrom.removeprefix('chr')}:{start:,}–{end:,} · "
            f"Source region: {site['regionType']} · CFD: {site['cfdOfftargetScore']:.3f}"
        )
        timing_status = st.empty()
        details_tab, genes_tab, exons_tab, direct_tab, gene_tab, summary_tab = st.tabs([
            "Site Details", "Genes & Function", "Exons",
            "ClinVar Site Overlaps", "ClinVar Gene Context", "Evidence Summary"
        ])
        genes, exons, clinvar_result = None, None, None
        gene_detail_failures = []
        gene_clinvar_failures = []

        with details_tab:
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

        # Keep static site details visible while the independent REST calls run.
        # All Streamlit/cache/UI work stays on this script's thread.
        with st.spinner("Retrieving Ensembl and NCBI annotations in parallel..."):
            try:
                annotations = load_site_annotations(chrom, start, end)
            except IncompleteAnnotations as error:
                annotations = error.results
        timing_status.caption(
            f"Original fetch: {annotations['retrieved_at']} (UTC) · "
            f"Total parallel lookup time: {annotations['elapsed_seconds']:.3f} s. "
            "Cached results reuse these original timings."
        )

        with genes_tab:
            st.subheader("Ensembl Gene Annotations")
            display_lookup_timing(annotations, ("genes",))

            with st.spinner("Retrieving annotations from Ensembl..."):

                try:
                    genes = annotation_value(annotations, ("genes",))

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

            st.subheader("Gene Information and Biological Function")

            if genes is None:
                st.info("Gene information is unavailable because the Ensembl overlap query failed. Retry the analysis.")

            elif not genes:

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

                    # Handle failures outside the cache so a later run can retry.
                    try:
                        gene_info = annotation_value(annotations, ("gene_information", gene_id))
                    except (RequestException, ValueError) as error:
                        gene_detail_failures.append(gene_id)
                        st.warning(
                            f"Detailed Ensembl information is unavailable for {gene_id}. "
                            "Showing metadata from the overlap query instead. "
                            "Select Analyze selected site to retry."
                        )
                        st.caption(f"Lookup details: {error}")
                        gene_info = {
                            **gene,
                            "gene_name": gene.get("gene_name") or "Unknown",
                            "description": "Detailed description unavailable because the Ensembl lookup failed.",
                        }

                    gene_symbol = gene_info["gene_name"]

                    if gene_symbol.lower() == "unknown":
                        display_name = (
                            f"Unnamed {gene_info['biotype']} "
                            f"({gene_info['gene_id']})"
                        )
                    else:
                        display_name = gene_symbol

                    st.markdown(f"### {display_name}")
                    display_lookup_timing(annotations, ("gene_information", gene_id))

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

                        ncbi_key = ("ncbi_summary", gene_symbol)
                        display_lookup_timing(annotations, ncbi_key)
                        ncbi_gene = annotations["values"].get(ncbi_key)
                        if ncbi_key in annotations["errors"]:
                            st.warning(f"NCBI biological function is unavailable for {gene_symbol}. Retry the analysis.")
                            st.caption(annotations["errors"][ncbi_key])
                        elif ncbi_gene:

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

        with exons_tab:
            st.subheader("Ensembl Exon Annotations")
            display_lookup_timing(annotations, ("exons",))

            with st.spinner("Retrieving exon annotations..."):

                try:
                    exons = annotation_value(annotations, ("exons",))

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

        with direct_tab:
            st.subheader("ClinVar Variant Annotations")
            display_lookup_timing(annotations, ("clinvar",))

            with st.spinner("Retrieving ClinVar annotations..."):

                try:
                    clinvar_result = annotation_value(annotations, ("clinvar",))

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

        with gene_tab:
            st.subheader("Gene-Level ClinVar Context")

            # Store gene-level ClinVar results for the evidence summary
            gene_clinvar_results = []

            if genes is None:
                st.info("Gene-level ClinVar context is unavailable because the Ensembl overlap query failed.")
            elif not genes:
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
                    display_lookup_timing(annotations, ("gene_clinvar", gene["gene_id"]))

                    try:
                        gene_clinvar = annotation_value(annotations, ("gene_clinvar", gene["gene_id"]))
                    except RequestException as error:
                        gene_clinvar_failures.append(gene_symbol)
                        st.warning(f"ClinVar gene context is unavailable for {gene_symbol}. Retry the analysis.")
                        st.caption(str(error))
                        continue
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

        with summary_tab:
            if gene_clinvar_failures:
                st.warning("Gene-level ClinVar evidence is incomplete for " + ", ".join(gene_clinvar_failures) + ".")
            if gene_detail_failures:
                st.warning(
                    "Detailed gene information could not be retrieved for "
                    + ", ".join(gene_detail_failures)
                    + ". Gene overlap evidence is available; the Genes & function tab shows the fallback metadata."
                )
            if genes is None or exons is None or clinvar_result is None:
                st.warning("Evidence summary is incomplete because an annotation service could not be reached. See the annotation tabs for details and retry the analysis.")
            else:
                evidence_column, interpretation_column = st.columns([1, 1], gap="large")
                with evidence_column:
                    st.subheader("Integrated evidence summary")

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

                    if gene_clinvar_failures:
                        gene_clinvar_matches = "Unavailable (incomplete lookup)"
                        gene_clinvar_examined = "Unavailable (incomplete lookup)"
                        gene_clinvar_verified = "Unavailable (incomplete lookup)"

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

                    st.dataframe(summary_df, hide_index=True, width="stretch", height=425,
                                 alt="Integrated evidence for the analyzed off-target site")

                    # ----------------------------------------
                    # Evidence Interpretation
                    # ----------------------------------------


                with interpretation_column:
                    st.subheader("Evidence at a glance")
                    st.write("**Overlapping genes:**", gene_summary)
                    st.write("**Overlapping exons:**", exon_summary)
                    st.write("**Verified exact-site ClinVar overlaps:**", direct_clinvar_count)
                    st.write("**Verified variants elsewhere in gene(s):**", gene_clinvar_verified)
                    st.caption(
                        "Gene-level context examines up to five records per named gene. "
                        "Counts across genes are summed and may include shared records."
                    )
                    st.info(
                        "These are computational predictions and existing annotations. "
                        "They do not establish that editing occurred or that a site is safe or harmful."
                    )
                    with st.expander("Full interpretation & limitations"):
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
                        if gene_clinvar_failures:
                            st.info("Gene-level clinical context is incomplete because a ClinVar lookup failed. Retry the analysis before interpreting the gene-level counts.")
                        elif not gene_clinvar_results:

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
