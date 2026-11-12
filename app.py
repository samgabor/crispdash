import streamlit as st
import pandas as pd
from pathlib import Path
import plotly.express as px
from services.dataset import load_selected_offtargets
from services.annotation_cache import AnnotationCache
from ui.analysis_results import render_annotation_results
from services.clinvar import CLINVAR_GENE_RECORD_LIMIT

from services.annotations import (
    collect_annotations, IncompleteAnnotations
)

st.set_page_config(
    page_title="CRISPR Off-Target Dashboard", page_icon="🧬",
    layout="wide", initial_sidebar_state="expanded"
)

PROJECT_ROOT = Path(__file__).resolve().parent

DATA_FILE = PROJECT_ROOT / "data" / "Selected-CRISPOR-Guide-OffTargets.csv"
EXPLORE_TAB = "Explore Sites"
ANALYSIS_TAB = "Site Analysis"

@st.cache_data
def load_data(file_version):
    # File modification time invalidates the cache when the seed CSV changes.
    return load_selected_offtargets(DATA_FILE)


@st.cache_resource
def get_annotation_cache():
    return AnnotationCache(ttl=3600)


def load_site_annotations(chrom, start, end, gene_record_limit, on_update=None):
    # Earlier snapshots lack the ClinVar verification breakdown.
    key = ("clinvar-verification-v1", chrom, start, end, gene_record_limit)
    cache = get_annotation_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached
    results = collect_annotations(
        chrom, start, end, gene_record_limit=gene_record_limit, on_update=on_update
    )
    if results["errors"]:
        raise IncompleteAnnotations(results)
    cache.put(key, results)
    return results



try:
    df = load_data(DATA_FILE.stat().st_mtime_ns)
except (OSError, ValueError) as error:
    st.error(f"Unable to load the selected CRISPOR dataset: {error}")
    st.stop()

st.session_state.setdefault("analyzed_site", None)
# Normalize older tab labels from existing browser sessions.
st.session_state["main_tab"] = {
    EXPLORE_TAB.casefold(): EXPLORE_TAB,
    ANALYSIS_TAB.casefold(): ANALYSIS_TAB,
}.get(str(st.session_state.get("main_tab", EXPLORE_TAB)).casefold(), EXPLORE_TAB)


def select_table_site(site_ids, table_key):
    """Map the selected display row to its site before the widgets rerun."""
    cells = st.session_state[table_key]["selection"]["cells"]
    if cells:
        st.session_state["selected_site"] = site_ids[cells[0][0]]
        st.session_state["main_tab"] = EXPLORE_TAB


def analyze_selected_site():
    st.session_state["analyzed_site"] = st.session_state["selected_site"]
    st.session_state["main_tab"] = ANALYSIS_TAB


def reset_guide_filters():
    st.session_state["min_cfd"] = 0.0
    st.session_state["region_filter"] = "All Regions"
    st.session_state["selected_site"] = None
    st.session_state["analyzed_site"] = None
    st.session_state["main_tab"] = EXPLORE_TAB


with st.sidebar:
    st.header("Guide & Filters")
    selected_guide = st.selectbox(
        "Guide RNA", df["name"].drop_duplicates().tolist(), key="guide",
        accept_new_options=False, filter_mode=None,
        on_change=reset_guide_filters,
        help="Select a guide from the CRISPOR seed dataset."
    )
    guide_df = df[df["name"] == selected_guide].copy()
    guide_metadata = guide_df.iloc[0]
    st.caption(f"Target: {guide_metadata['target']} · Genome: {guide_metadata['genome']}")
    st.caption(f"Disease: {guide_metadata['disease']}")
    with st.expander("Guide sequence & source"):
        st.code(guide_metadata["guideSeq"], language=None)
        st.caption("Guide-target DNA including PAM (Protospacer Adjacent Motif, a short DNA sequence required for Cas9 to recognize and bind to target DNA), as supplied in the selected CRISPOR dataset.")
        st.write("Target position:", guide_metadata["position"])
        st.caption("Source: CRISPOR")

    st.link_button(
        f"Open {selected_guide} in CRISPOR",
        guide_metadata["crispor"],
        width="stretch",
        help="Open the results URL supplied for this guide in the seed dataset."
    )

    min_cfd = st.slider(
        "Minimum CFD (Cutting Frequency Determination) score", min_value=0.0, max_value=1.0, step=0.01, key="min_cfd",
        help="Show sites at or above this sequence-based off-target score."
    )
    region_filter = st.selectbox(
        "Source genomic region", ["All Regions", "Intergenic", "Intron", "Exon"],
        accept_new_options=False, filter_mode=None,
        key="region_filter", help="Region labels supplied in the selected CRISPOR dataset."
    )

filtered_df = guide_df[guide_df["cfdOfftargetScore"] >= min_cfd].copy()
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
    st.caption(f"{len(filtered_df)} of {len(guide_df)} sites match the filters.")

st.title("🧬 CRISPR Off-Target Dashboard")
st.caption(
    f"{selected_guide} · {guide_metadata['target']} · {guide_metadata['disease']} · "
    f"{guide_metadata['genome']} · Computational predictions and genomic annotations"
)

metric_grid = st.grid(4, min_column_width=160)
for label, value in [
    ("Predicted Sites", len(guide_df)),
    ("Median CFD Score", f"{guide_df['cfdOfftargetScore'].median():.4f}"),
    ("Maximum CFD Score", f"{guide_df['cfdOfftargetScore'].max():.4f}"),
    ("Matching Sites", len(filtered_df)),
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
            table_key = f"site_table_{selected_guide}"
            display_df = filtered_df.copy()
            display_df["offtargetSeq"] = display_df["offtargetSeq"].map(
                lambda sequence: sequence[:-3] + sequence[-3:].lower()
            )
            st.dataframe(
                display_df, column_order=[
                    "siteId", "chrom", "start", "end", "cfdOfftargetScore",
                    "mismatchCount", "offtargetSeq", "regionType", "locusDesc"
                ], width="stretch", hide_index=True, height=365,
                column_config={
                    "siteId": st.column_config.TextColumn(label='SiteId', width=100, pinned=True),
                    "chrom": st.column_config.TextColumn(label='Chr#', width=100, pinned=False),
                    "start": st.column_config.TextColumn(label='Start', width=100, pinned=False),
                    "end": st.column_config.TextColumn(label='End', width=100, pinned=False),
                    "cfdOfftargetScore": st.column_config.NumberColumn(label='CFD',width=100),
                    "mismatchCount": st.column_config.NumberColumn(label='MisMatch',width=100),
                    "offtargetSeq": st.column_config.TextColumn(label='OffTargetSeq',width=270),
                    "regionType": st.column_config.TextColumn(label='Region',width=110),
                    "locusDesc": st.column_config.TextColumn(label='Desc',width=350),
                },
                key=table_key, selection_mode="single-cell",
                on_select=lambda: select_table_site(site_options, table_key),
                alt="Predicted off-target sites matching the sidebar filters"
            )
        st.caption("Scroll horizontally within the table to view the sequence and locus. Site IDs stay visible.")
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
        site = guide_df[guide_df["siteId"] == selected_site].iloc[0]
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

        slots = {
            "genes": genes_tab.empty(), "exons": exons_tab.empty(),
            "direct": direct_tab.empty(), "gene": gene_tab.empty(),
            "summary": summary_tab.empty(),
        }

        def show_progress(snapshot):
            render_annotation_results(snapshot, site, selected_site, slots, timing_status)

        try:
            annotations = load_site_annotations(
                chrom, start, end, CLINVAR_GENE_RECORD_LIMIT, on_update=show_progress
            )
        except IncompleteAnnotations as error:
            annotations = error.results
        # A cache hit skips the REST work and immediately renders the final snapshot.
        show_progress(annotations)
