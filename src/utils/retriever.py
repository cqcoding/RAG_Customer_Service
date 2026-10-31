from src.utils.create_db import get_vector_store


def get_retriever():
    return get_vector_store().as_retriever(
        search_type="mmr",
        search_kwargs={"k": 6, "fetch_k": 25}
    )
