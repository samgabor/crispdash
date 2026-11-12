"""Render ready annotation results into independent tab placeholders."""
import re
from urllib.parse import quote
import pandas as pd
import streamlit as st
from requests.exceptions import RequestException
import config
from services.annotations import annotation_value
from services.clinvar import CLINVAR_GENE_RECORD_LIMIT

VERIFICATION_LABELS = {
    "classification_excluded": "Excluded: clinical classification",
    "missing_grch38": "Excluded: missing GRCh38 coordinates",
    "missing_gene_boundaries": "Excluded: missing Ensembl gene boundaries",
    "outside_gene": "Excluded: outside Ensembl gene interval",
    "direct_overlap": "Directly overlapping variants",
    "verified_elsewhere": "Verified variants elsewhere in the gene",
}


def display_clinvar_verification(result):
    """Explain the examined sample; send record-level diagnostics only in debug mode."""
    st.write("**Directly overlapping ClinVar variants:**",
             result.get("direct_overlap_count", len(result.get("direct_overlaps", []))))
    st.caption(
        "Direct overlaps here are qualifying records from this gene search sample; "
        "the ClinVar Site Overlaps tab performs a separate region search."
    )
    if result.get("truncated", result["records_examined"] < result["search_count"]):
        st.warning(
            f"Only {result['records_examined']} of {result['search_count']} ClinVar search "
            "matches were examined. These results are not exhaustive."
        )
    if result.get("gene_boundaries_available") is False:
        st.warning(
            "Ensembl gene boundaries were unavailable, so variants elsewhere in the gene "
            "could not be verified by genomic coordinates."
        )
    if not result["gene_variants"]:
        st.info(
            "No qualifying ClinVar variants elsewhere in the selected Ensembl gene interval "
            "were verified among the records examined. This does not establish that the "
            "gene has no pathogenic variants."
        )
    # Older cached snapshots have no breakdown; never invent zero exclusions for them.
    if "verification_outcomes" not in result:
        return
    with st.expander("ClinVar Verification Details"):
        rows = [{"Verification outcome": label, "Count": result[f"{outcome}_count"]}
                for outcome, label in VERIFICATION_LABELS.items()]
        rows.append({"Verification outcome": "Total records examined",
                     "Count": result["records_examined"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     alt="ClinVar verification outcome counts for this gene")
        st.caption(
            "Each examined record appears in exactly one outcome. Classification is checked "
            "first, then GRCh38 coordinates, direct overlap, gene boundaries, and gene overlap. "
            "A missing-coordinate exclusion means verification was unavailable."
        )
    if config.DEBUG and result["verification_outcomes"]:
        with st.expander("ClinVar per-record verification (debug)"):
            rows = [{
                "Variation ID": record["variant_id"],
                "Variant": record["title"],
                "Original classification": record["clinical_significance"],
                "Verification outcome": VERIFICATION_LABELS[record["outcome"]],
            } for record in result["verification_outcomes"]]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         alt="Per-record ClinVar verification outcomes for debugging")


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
    if config.DEBUG and requests:
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


def render_annotation_results(annotations, site, selected_site, slots, timing_status):
    def ready(key):
        return key in annotations["values"] or key in annotations["errors"]

    genes = annotations["values"].get(("genes",))
    exons = annotations["values"].get(("exons",))
    clinvar_result = annotations["values"].get(("clinvar",))
    chrom, start, end = str(site["chrom"]), int(site["start"]), int(site["end"])
    gene_detail_failures = []
    gene_clinvar_failures = []
    gene_clinvar_results = []
    if annotations.get("complete", True):
        timing_status.caption(
            f"Original fetch: {annotations['retrieved_at']} (UTC) · "
            f"Total parallel lookup time: {annotations['elapsed_seconds']:.3f} s. "
            "Cached results reuse these original timings."
        )
    else:
        timing_status.caption(
            f"Loading annotations: {len(annotations['timings'])} lookup(s) complete, "
            f"{len(annotations.get('pending', []))} running or queued. "
            "Open any tab to view the results already available."
        )

    with slots["genes"].container():
        if not ready(("genes",)):
            st.info('Loading Ensembl gene overlaps...')
        else:
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

                    if not ready(("gene_information", gene_id)):
                        st.info(f"Loading gene details for {gene_id}...")
                        continue

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
                        if not ready(ncbi_key):
                            st.info(f"Loading biological function for {gene_symbol}...")
                        elif ncbi_key in annotations["errors"]:
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

    with slots["exons"].container():
        if not ready(("exons",)):
            st.info('Loading Ensembl exon overlaps...')
        else:
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

    with slots["direct"].container():
        if not ready(("clinvar",)):
            st.info('Loading ClinVar site overlaps...')
        else:
            st.subheader("ClinVar Variant Annotations")
            st.caption(
                "This tab reports the genomic-region search. Gene searches can return additional "
                "records with verified direct overlaps; those counts appear in ClinVar Gene Context."
            )
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

    with slots["gene"].container():
        if not ready(("genes",)):
            st.info('Waiting for overlapping genes...')
        else:
            st.subheader("Gene-Level ClinVar Context")
            st.caption(
                f"Sampling limit: only the first {CLINVAR_GENE_RECORD_LIMIT} records returned "
                "by the pathogenic/likely pathogenic ClinVar search are examined per gene "
                "(or all returned records when fewer are available). This is not an exhaustive review."
            )

            # Store gene-level ClinVar results for the evidence summary
            gene_clinvar_results = []
            gene_variant_rows = []
            seen_variant_ids = set()

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

                    if not ready(("gene_clinvar", gene["gene_id"])):
                        st.info(f"Loading ClinVar context for {gene_symbol}...")
                        continue

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
                    display_clinvar_verification(gene_clinvar)

                    for variant in gene_clinvar["gene_variants"]:
                        variant_id = str(variant["variant_id"])
                        if variant_id in seen_variant_ids:
                            continue
                        seen_variant_ids.add(variant_id)
                        title = re.sub(r"([\\`*_\[\]<>])", r"\\\1", str(variant["title"]))
                        variant_url = (
                            "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
                            f"{quote(variant_id, safe='')}/"
                        )
                        gene_variant_rows.append({
                            "Variant": f"[{title}]({variant_url})",
                            "Clinical significance": variant["clinical_significance"],
                            "Review status": variant["review_status"],
                        })

            if gene_variant_rows:
                st.caption(
                    f"Showing {len(gene_variant_rows)} unique ClinVar variants across "
                    "all overlapping genes. Click a variant description to open its record."
                )
                with st.container(height=450, border=False):
                    st.table(
                        pd.DataFrame(gene_variant_rows),
                        hide_index=True,
                        alt="Gene-level ClinVar variants across all overlapping genes"
                    )
            elif gene_clinvar_results and annotations.get("complete", True):
                st.info("No qualifying variants elsewhere in the gene were found among the records examined.")

            st.caption(
                "These ClinVar records are associated with the overlapping genes but "
                "do not overlap the selected off-target site. They provide gene-level "
                "clinical context, not evidence that CRISPR editing at this site "
                "would cause a clinical effect."
            )

    with slots["summary"].container():
        if not annotations.get("complete", True):
            st.info('Evidence summary will be available when all annotation lookups finish. Other tabs update as results arrive.')
        else:
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
                    st.caption(
                        "This overlap count comes from the genomic-region search. The ClinVar Gene "
                        "Context tab separately reports any direct overlaps verified from gene search matches."
                    )
                    st.write("**Verified variants elsewhere in gene(s):**", gene_clinvar_verified)
                    st.caption(
                        f"Gene-level context examines only the first {CLINVAR_GENE_RECORD_LIMIT} "
                        "returned records per named gene, or fewer when fewer are available. "
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
                                    "This does not establish that these genes have no pathogenic "
                                    "variants. See ClinVar Verification Details for the outcome "
                                    "of each verification stage and any search limitations."
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
