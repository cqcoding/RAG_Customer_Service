import streamlit as st
import time
from io import StringIO
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.agents.orchestrator import workflow
from src.utils.create_db import add_file_to_chroma_db
import os

os.chdir(ROOT_DIR)  # Set working directory to project root


st.title("Interface RAG Customer Service")

input_usuario = st.text_input("Ask your question about the Music Emporium Store:")

if input_usuario:
    state = {
        "query": input_usuario,
        "classifications": [],
        "results": [],
        "final_answer": ""
    }
    state = workflow.invoke(state)
    with st.spinner("Aguarde...", show_time=True):
        time.sleep(5)
    st.success("Pronto!")
    st.button("Tentar novamente")
    st.write("A resposta é ", state.get("final_answer", ""))

