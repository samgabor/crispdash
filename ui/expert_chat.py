"""Session-local Expert Chat, independent of annotation requests."""
import streamlit as st

from services.expert_chat import (build_evidence, conversation_key, new_conversation,
                                  public_error, send_agent_message)


def _show_message(message):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("elapsed_seconds") is not None:
            st.caption(f"Agent response time: {message['elapsed_seconds']:.3f} s · "
                       f"Received: {message['received_at']} (UTC)")
        if message.get("sources"):
            with st.expander("Agent source references"):
                for source in message["sources"]:
                    if source.get("url"):
                        st.link_button(source["title"], source["url"])
                    else:
                        st.write(source["title"])
                        st.caption(f"Foundry grounding file: {source.get('file_id', '')}")


@st.fragment
def render_expert_chat(settings, annotations, site, guide, include_other=False):
    st.subheader("Expert Chat")
    if not annotations.get("complete", True) or annotations.get("pending"):
        st.info("Expert Chat will be available when all annotation requests have finished.")
        return
    packet = build_evidence(annotations, site, guide, include_other)
    key = conversation_key(settings, str(guide["name"]), str(site["siteId"]))
    conversations = st.session_state.setdefault("expert_conversations", {})
    if key not in conversations:
        conversations[key] = new_conversation(packet)
    conversation = conversations[key]
    changed = packet["id"] != conversation["evidence_id"]
    st.caption(f"{guide['name']} · {site['siteId']} · Agent: {settings.agent_name}")
    st.caption("Research support, not a determination that a site is safe or suitable for clinical use. "
               "Generate Site Assessment sends this site's prepared evidence to your Azure agent. "
               "Conversations are retained separately for each guide/site during this dashboard session.")
    if annotations["errors"]:
        failed = ", ".join(" / ".join(key) for key in sorted(annotations["errors"]))
        st.warning("Some annotation lookups failed: " + failed + ". The agent will be told "
                   "which evidence is missing; an assessment is still available.")
    if changed:
        st.warning("The evidence or filters changed since this conversation started. "
                   "The conversation below refers to its original snapshot. "
                   "Select Start New Conversation to use the current evidence.")
    if st.button("Start New Conversation", key=f"expert_reset_{key}",
                 disabled=not (conversation["messages"] or conversation["pending_turn"] or changed)):
        fresh = new_conversation(packet)
        fresh["revision"] = conversation["revision"] + 1
        conversations[key] = fresh
        st.rerun()
    with st.expander("Prepared evidence for this conversation"):
        st.caption("This snapshot stays fixed throughout the conversation. Full source records "
                   "remain available in the annotation tabs.")
        st.json(conversation["packet"]["evidence"], expanded=False)
    if conversation["packet"]["evidence"]["omissions"]:
        st.caption("The prepared evidence includes explicit size limits and omission counts. "
                   "Open Prepared evidence to review what was included.")
    for message in conversation["messages"]:
        _show_message(message)
    retry = False
    if conversation["pending_turn"]:
        st.error(conversation["error"] or "The previous request did not finish locally. "
                 "Its server-side outcome is unknown. Retrying may create another response.")
        retry = st.button("Retry Last Message", key=f"expert_retry_{key}", disabled=changed)
    generate = st.button("Generate Site Assessment", key=f"expert_generate_{key}",
                         type="primary", disabled=bool(conversation["messages"] or
                                                       conversation["pending_turn"] or changed))
    prompt = st.chat_input("Ask about this off-target site", key=f"expert_input_{key}_{conversation['revision']}",
                           disabled=not conversation["messages"] or changed or
                                    bool(conversation["pending_turn"]),
                           submit_mode="disable", max_chars=8000)
    if generate:
        conversation["pending_turn"] = {"display": "Assess this off-target site and recommend next steps.",
                                         "input": conversation["packet"]["prompt"]}
    elif prompt:
        conversation["pending_turn"] = {"display": str(prompt), "input": str(prompt)}
    if not (generate or prompt or retry):
        return
    turn = conversation["pending_turn"]
    with st.chat_message("user"):
        st.write(turn["display"])
    cursor = st.empty()
    try:
        cursor.html('<span id="expert-network-busy" hidden></span><style>'
                    'html:has(#expert-network-busy), html:has(#expert-network-busy) *'
                    '{cursor:progress !important;}</style>')
        with st.spinner("Waiting for the Azure agent…", show_time=True):
            answer = send_agent_message(settings, turn["input"],
                                        conversation["previous_response_id"],
                                        conversation["agent_session_id"])
        conversation["messages"].extend([
            {"role": "user", "content": turn["display"]},
            {"role": "assistant", "content": answer["text"], "sources": answer["sources"],
             "elapsed_seconds": answer["elapsed_seconds"], "received_at": answer["received_at"]},
        ])
        conversation["previous_response_id"] = answer["response_id"]
        conversation["agent_session_id"] = answer["agent_session_id"]
        conversation["pending_turn"] = None
        conversation["error"] = None
    except Exception as error:
        conversation["error"] = public_error(error)
    finally:
        cursor.empty()
    st.rerun()
