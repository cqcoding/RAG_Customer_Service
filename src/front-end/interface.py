import os
import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)  

from src.agents.orchestrator import answer  # noqa: E402

st.set_page_config(page_title="Music Emporium Store")
st.title("Interface RAG Customer Service")

# Chat history for this browser session, so follow-up questions keep context.
st.session_state.setdefault("messages", [])

with st.sidebar:
    if st.button("Nova conversa", disabled=not st.session_state.messages):
        st.session_state.messages = []
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask your question about the Music Emporium Store:"):
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Aguarde...", show_time=True):
            reply = answer(prompt, history=st.session_state.messages)
        st.markdown(reply)

    st.session_state.messages += [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": reply},
    ]
