"""Multi-guide seed loading and guide-switch behavior, without live API calls."""
from pathlib import Path
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from services.dataset import load_selected_offtargets


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "Selected-CRISPOR-Guide-OffTargets.csv"


class MultiGuideTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.data = load_selected_offtargets(DATA)

    def test_each_guide_controls_sites_metrics_metadata_and_link(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        names = self.data["name"].drop_duplicates().tolist()
        self.assertEqual(app.selectbox(key="guide").options, names)
        for name in names:
            app.selectbox(key="guide").select(name).run()
            self.assertFalse(app.exception, app.exception)
            expected = self.data[self.data["name"] == name]
            self.assertEqual(app.selectbox(key="selected_site").options, expected["siteId"].tolist())
            self.assertEqual(int(app.metric[0].value), len(expected))
            self.assertEqual(int(app.metric[1].value), int(expected["regionType"].eq("exon").sum()))
            table = next(f.value for f in app.dataframe if "siteId" in f.value.columns)
            self.assertEqual(set(table["name"]), {name})
            link = next(link for link in app.get("link_button") if "CRISPOR" in link.proto.label)
            self.assertEqual(link.proto.url, expected.iloc[0]["crispor"])
            self.assertTrue(any(expected.iloc[0]["target"] in c.value for c in app.caption))
            self.assertTrue(any(expected.iloc[0]["disease"] in c.value for c in app.caption))

    def test_guide_change_resets_filters_analysis_and_empty_site_picker(self):
        empty = {
            "values": {("genes",): [], ("exons",): [], ("clinvar",): {
                "verified_variants": [], "search_count": 0, "truncated": False}},
            "errors": {}, "timings": {}, "elapsed_seconds": 0.1,
            "retrieved_at": "2026-11-11T12:00:00+00:00",
        }
        with patch("services.annotations.collect_annotations", return_value=empty) as lookup:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.button(key="analyze").click().run()
            self.assertEqual(app.session_state["main_tab"], "Site Analysis")
            app.slider(key="min_cfd").set_value(1.0).run()
            app.selectbox(key="region_filter").select("Exon").run()
            self.assertTrue(app.button(key="analyze").disabled)
            app.selectbox(key="guide").select("CFTR-sgRNA-1").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.slider(key="min_cfd").value, 0.0)
            self.assertEqual(app.selectbox(key="region_filter").value, "All Regions")
            self.assertIsNone(app.session_state["analyzed_site"])
            self.assertEqual(app.session_state["main_tab"], "Explore Sites")
            self.assertEqual(app.selectbox(key="selected_site").value, "SITE-416")
            self.assertEqual(lookup.call_count, 1)
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any(s.value == "Analysis: SITE-416" for s in app.subheader))
            self.assertEqual(lookup.call_args.args, ("chr1", 48980407, 48980429))

    def test_unique_names_populate_new_guides_automatically(self):
        extra = self.data.iloc[[0]].copy()
        extra["name"] = "Another guide"
        import pandas as pd
        expanded = pd.concat([self.data, extra], ignore_index=True)
        with patch("services.dataset.load_selected_offtargets", return_value=expanded):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            self.assertFalse(app.exception, app.exception)
            self.assertIn("Another guide", app.selectbox(key="guide").options)

    def test_conflicting_metadata_is_rejected(self):
        broken = self.data.rename(columns={"siteId": "siteid", "regionType": "region"}).copy()
        broken.loc[0, "crispor"] = "https://example.org/conflicting"
        with patch("services.dataset.pd.read_csv", return_value=broken):
            with self.assertRaisesRegex(ValueError, "Conflicting guide metadata"):
                load_selected_offtargets(DATA)


if __name__ == "__main__":
    unittest.main()
