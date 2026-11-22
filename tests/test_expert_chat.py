"""Offline Expert Chat coverage: credentials never reach prompts, logs, or the browser."""
from copy import deepcopy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from services.expert_chat import (AZURE_FIELDS, ChatSettings, build_evidence,
                                  conversation_key, get_chat_settings, public_error,
                                  send_agent_message)
from tests.test_search_parameters import APP, empty_snapshot


ENV = dict(zip(AZURE_FIELDS, ["https://example.services.ai.azure.com/api/projects/project",
                             "CRISPOR-Expert", "tenant", "client", "secret-do-not-display"]))
SETTINGS = ChatSettings(*ENV.values())


def snapshot():
    result = empty_snapshot(gene_record_limit=100, site_record_limit=1000)
    result["complete"] = True
    result["pending"] = []
    return result


def reply(response_id="r1", session_id="s1", text="Research assessment"):
    return dict(text=text, response_id=response_id, agent_session_id=session_id,
                sources=[], elapsed_seconds=0.2, received_at="test response time")


def page(annotations, guide="G", site_id="SITE-001"):
    from services.expert_chat import ChatSettings
    from ui.expert_chat import render_expert_chat
    settings = ChatSettings("https://example.services.ai.azure.com/api/projects/project",
                            "CRISPOR-Expert", "tenant", "client", "secret")
    render_expert_chat(settings, annotations, {"siteId": site_id, "chrom": "1", "start": 1, "end": 23},
                       {"name": guide})


def button(app, label):
    return next(item for item in app.button if item.label == label)


class ExpertEvidenceTests(unittest.TestCase):
    def test_all_five_settings_required_and_trimmed(self):
        with patch.dict(os.environ, ENV):
            self.assertIsNotNone(get_chat_settings())
            for key in AZURE_FIELDS:
                with self.subTest(key=key), patch.dict(os.environ, {key: "  "}):
                    self.assertIsNone(get_chat_settings())
            with patch.dict(os.environ, {"AGENT_NAME": "  CRISPOR-Expert  "}):
                self.assertEqual(get_chat_settings().agent_name, "CRISPOR-Expert")
        self.assertNotIn(ENV["AZURE_CLIENT_SECRET"], repr(SETTINGS))

    def test_prompt_contains_sources_counts_limits_and_sanitized_failures(self):
        data = snapshot()
        data["errors"][("uniprot", "GENE")] = "Failure with api-key=secret-do-not-display"
        data["timings"][("genes",)] = {"requests": ["secret-do-not-display"]}
        data["values"][("clinvar",)]["verified_variants"] = [
            {"clinvar_id": "123", "clinical_significance": "Pathogenic"},
            {"clinvar_id": "456", "clinical_significance": "association"}]
        packet = build_evidence(data, {"siteId": "SITE-1", "offtargetSeq": "ACTGagg"}, {"name": "Guide"})
        evidence = packet["evidence"]
        self.assertEqual(evidence["region_verified_overlap_count"], 2)
        self.assertEqual(evidence["region_displayed_overlap_count"], 1)
        self.assertEqual(evidence["failed_lookups"], [["uniprot", "GENE"]])
        self.assertEqual(evidence["search_parameters"]["gene_record_limit"], 100)
        self.assertIn("ACTGagg", packet["prompt"])
        self.assertNotIn("secret-do-not-display", packet["prompt"])
        self.assertIn("untrusted data", packet["prompt"])
        self.assertNotIn("timings", evidence)

    def test_context_changes_are_detected_and_omissions_explicit(self):
        data = snapshot()
        data["values"][("ncbi_summary", "TEST")] = {"text": "x" * 7000, "records": list(range(50))}
        first = build_evidence(data, {"siteId": "SITE-1", "empty": float("nan")}, {"name": "G"})
        self.assertTrue(first["evidence"]["omissions"])
        self.assertIsNone(first["evidence"]["selected_site"]["empty"])
        self.assertEqual(json.loads(json.dumps(first))["id"], first["id"])
        second = build_evidence(data, {"siteId": "SITE-1", "empty": float("nan")}, {"name": "G"}, True)
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(conversation_key(SETTINGS, "G", "SITE-1"),
                            conversation_key(SETTINGS, "OTHER", "SITE-1"))

    def test_pending_requests_cannot_generate_evidence(self):
        data = snapshot()
        data["pending"] = [("clinvar",)]
        with self.assertRaises(ValueError):
            build_evidence(data, {}, {})
        data["pending"] = []
        data["complete"] = False
        with self.assertRaises(ValueError):
            build_evidence(data, {}, {})


class ExpertServiceTests(unittest.TestCase):
    def test_sdk_matches_working_protocol_and_preserves_both_ids(self):
        response = SimpleNamespace(output_text="An assessment", id="new-response",
                                   model_extra={"agent_session_id": "new-session"}, output=[])
        with patch("azure.identity.ClientSecretCredential") as credential, \
             patch("azure.identity.get_bearer_token_provider", return_value="token-provider") as provider, \
             patch("openai.OpenAI") as client:
            instance = client.return_value.__enter__.return_value
            instance.responses.create.return_value = response
            result = send_agent_message(SETTINGS, "evidence", "prior-response", "prior-session")
        self.assertEqual(client.call_args.kwargs["base_url"], SETTINGS.endpoint)
        self.assertEqual(client.call_args.kwargs["default_query"], {"api-version": "v1"})
        self.assertEqual(client.call_args.kwargs["api_key"], "token-provider")
        self.assertEqual(client.call_args.kwargs["max_retries"], 0)
        provider.assert_called_once_with(credential.return_value.__enter__.return_value,
                                         "https://ai.azure.com/.default")
        request = instance.responses.create.call_args.kwargs
        self.assertEqual(request["previous_response_id"], "prior-response")
        self.assertEqual(request["extra_body"], {"agent_session_id": "prior-session"})
        self.assertEqual(result["response_id"], "new-response")
        self.assertEqual(result["agent_session_id"], "new-session")
        credential.return_value.__exit__.assert_called_once()
        client.return_value.__exit__.assert_called_once()

    def test_initial_request_and_citations_and_session_fallback(self):
        annotations = [SimpleNamespace(model_dump=lambda: {"type": "url_citation", "title": "Evidence",
                                                            "url": "https://example.org/evidence"}),
                       SimpleNamespace(model_dump=lambda: {"type": "file_citation", "filename": "Guide.pdf",
                                                            "file_id": "file1"})]
        response = SimpleNamespace(output_text="Assessment", id="r1", model_extra={},
                                   output=[SimpleNamespace(content=[SimpleNamespace(annotations=annotations)])])
        with patch("azure.identity.ClientSecretCredential"), \
             patch("azure.identity.get_bearer_token_provider"), patch("openai.OpenAI") as client:
            instance = client.return_value.__enter__.return_value
            instance.responses.create.return_value = response
            result = send_agent_message(SETTINGS, "evidence", agent_session_id="existing-session")
        self.assertNotIn("previous_response_id", instance.responses.create.call_args.kwargs)
        self.assertEqual(result["agent_session_id"], "existing-session")
        self.assertEqual(len(result["sources"]), 2)

    def test_errors_never_echo_sensitive_exception_text(self):
        for status in [401, 403, 404, 429, 500]:
            error = RuntimeError("client_secret=secret-do-not-display")
            error.status_code = status
            self.assertNotIn("secret-do-not-display", public_error(error))


class ExpertUITests(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()
        st.cache_data.clear()
        self.addCleanup(st.cache_resource.clear)
        self.addCleanup(st.cache_data.clear)

    def test_hidden_when_any_setting_missing_and_position_when_enabled(self):
        for enabled in [False, True]:
            with self.subTest(enabled=enabled), patch.dict(os.environ, ENV), \
                 patch("services.annotations.collect_annotations", side_effect=empty_snapshot), \
                 patch("ui.expert_chat.send_agent_message") as send:
                with patch.dict(os.environ, {} if enabled else {"AGENT_NAME": ""}):
                    app = AppTest.from_file(str(APP), default_timeout=20).run()
                    app.button(key="analyze").click().run()
                self.assertFalse(app.exception, app.exception)
                labels = [tab.label for tab in app.tabs]
                self.assertEqual("Expert Chat" in labels, enabled)
                if enabled:
                    self.assertEqual(labels.index("Expert Chat"), labels.index("Evidence Summary") + 1)
                send.assert_not_called()

    def test_pending_gate_and_failure_warning(self):
        pending = snapshot()
        pending["complete"] = False
        app = AppTest.from_function(page, args=(pending,)).run()
        self.assertFalse(app.exception, app.exception)
        self.assertFalse(app.button)
        failed = snapshot()
        failed["errors"][("uniprot", "TEST")] = "secret"
        app = AppTest.from_function(page, args=(failed,)).run()
        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any("Some annotation lookups failed" in w.value for w in app.warning))
        self.assertFalse(button(app, "Generate Site Assessment").disabled)

    def test_generate_followup_reset_and_no_automatic_calls(self):
        with patch("ui.expert_chat.send_agent_message", side_effect=[reply(), reply("r2", "s1"), reply("r3", "s3")]) as send:
            app = AppTest.from_function(page, args=(snapshot(),)).run()
            send.assert_not_called()
            button(app, "Generate Site Assessment").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(len(app.chat_message), 2)
            self.assertIn("BEGIN SITE EVIDENCE", send.call_args.args[1])
            app.chat_input[0].set_value("What evidence is missing?").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(send.call_args.args[1:], ("What evidence is missing?", "r1", "s1"))
            self.assertEqual(len(app.chat_message), 4)
            app.run()
            self.assertEqual(send.call_count, 2)
            button(app, "Start New Conversation").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(len(app.chat_message), 0)
            button(app, "Generate Site Assessment").click().run()
            self.assertEqual(send.call_args.args[2:], (None, None))

    def test_failed_turn_can_retry_without_advancing_ids(self):
        with patch("ui.expert_chat.send_agent_message", side_effect=[RuntimeError("secret"), reply()]) as send:
            app = AppTest.from_function(page, args=(snapshot(),)).run()
            button(app, "Generate Site Assessment").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(app.error)
            self.assertNotIn("secret", app.error[0].value)
            self.assertEqual(len(app.chat_message), 0)
            button(app, "Retry Last Message").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args.args[2:], (None, None))
            self.assertEqual(len(app.chat_message), 2)

    def test_chat_does_not_repeat_failed_rest_requests_and_preserves_site_history(self):
        def failed(*args, **kwargs):
            data = empty_snapshot(*args, **kwargs)
            data["errors"][("exons",)] = "Timeout"
            return data
        with patch.dict(os.environ, ENV), \
             patch("services.annotations.collect_annotations", side_effect=failed) as collect, \
             patch("ui.expert_chat.send_agent_message", return_value=reply()) as send:
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            app.button(key="analyze").click().run()
            button(app, "Generate Site Assessment").click().run()
            self.assertFalse(app.exception, app.exception)
            app.chat_input[0].set_value("Next steps?").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(collect.call_count, 1)
            app.selectbox(key="selected_site").select("SITE-002").run()
            app.button(key="analyze").click().run()
            self.assertEqual(len(app.chat_message), 0)
            app.selectbox(key="selected_site").select("SITE-001").run()
            app.button(key="analyze").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(len(app.chat_message), 4)
            self.assertEqual(send.call_count, 2)

    def test_new_evidence_requires_explicit_reset(self):
        with patch.dict(os.environ, ENV), \
             patch("services.annotations.collect_annotations", side_effect=empty_snapshot), \
             patch("ui.expert_chat.send_agent_message", return_value=reply()):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            app.button(key="analyze").click().run()
            button(app, "Generate Site Assessment").click().run()
            app.checkbox(key="clinvar_include_other").check().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any("evidence or filters changed" in w.value for w in app.warning))
            self.assertTrue(app.chat_input[0].disabled)
            button(app, "Start New Conversation").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertFalse(button(app, "Generate Site Assessment").disabled)


if __name__ == "__main__":
    unittest.main()
