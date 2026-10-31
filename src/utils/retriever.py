from src.config import get_settings
from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

def get_retriever():
    settings = get_settings()

    embed_model = FastEmbedEmbeddings(
        model_name="BAAI/bge-base-en-v1.5"
    )

    chroma_db = Chroma(
        collection_name="my_collection",
        persist_directory=settings.chroma_db_path,
        embedding_function=embed_model,
    )

    return chroma_db.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 6, "fetch_k": 25}
    )