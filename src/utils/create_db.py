"""
Build the Chroma vector store from the store policy PDF(s) in data/.

Run with:  python -m src.utils.create_db

The CSV tables are not embedded: they are loaded into PostgreSQL
(src/utils/create_sql_db.py) and queried by the SQL agent, which handles
joins and exact numbers far better than similarity search over rows.
"""
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_text_splitters import NLTKTextSplitter, RecursiveCharacterTextSplitter

from src.config import get_settings

load_dotenv()
DATA_PATH = Path(__file__).resolve().parents[2] / "data"
COLLECTION_NAME = "my_collection"
BATCH_SIZE = 25


def get_vector_store() -> Chroma:
    settings = get_settings()
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=FastEmbedEmbeddings(model_name=settings.embedding_model),
        persist_directory=settings.chroma_db_path,
    )


def add_metadata(documents):
    for doc in documents:
        source = Path(doc.metadata.get("source", ""))
        doc.metadata.update({
            "file_type": source.suffix.lower().lstrip("."),
            "document": source.stem,          # e.g. "políticas_da_loja"
            "doc_type": "store_policy",
        })
    return documents


def split_documents(documents):
    # Hybrid chunking: sentence-aware first, then capped at 600 characters.
    sentences = NLTKTextSplitter().split_documents(documents)
    chunker = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=80)
    return sentences, chunker.split_documents(sentences)


def add_chunks(chroma_db: Chroma, chunks) -> None:
    for i in range(0, len(chunks), BATCH_SIZE):
        chroma_db.add_documents(chunks[i:i + BATCH_SIZE])


def create_chroma_db():
    settings = get_settings()

    pdf_loader = DirectoryLoader(str(DATA_PATH), glob="**/*.pdf", loader_cls=PyPDFLoader)
    pdf_docs = add_metadata(pdf_loader.load())
    print(f"Sample metadata: {pdf_docs[0].metadata if pdf_docs else 'No documents'}")

    sentences, chunks = split_documents(pdf_docs)
    sizes = [len(c.page_content) for c in chunks]
    print("PDF pages:", len(pdf_docs))
    print("Sentences:", len(sentences))
    print("Chunks:", len(chunks))
    print("Chunk size — min / avg / max:", min(sizes), sum(sizes) // len(sizes), max(sizes))

    # Start from an empty collection so re-running doesn't duplicate chunks.
    chroma_db = get_vector_store()
    chroma_db.delete_collection()
    chroma_db = get_vector_store()
    add_chunks(chroma_db, chunks)

    print(f"Chroma DB created at {settings.chroma_db_path}")


def add_file_to_chroma_db(file_path: str) -> None:
    """Add one more policy PDF to the existing vector store."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"Unsupported file type: {path.suffix}. Only PDFs go into the vector store; "
            "store data (CSV) goes into PostgreSQL via src/utils/create_sql_db.py."
        )

    _, chunks = split_documents(add_metadata(PyPDFLoader(str(path)).load()))
    add_chunks(get_vector_store(), chunks)
    print(f"Added file to Chroma DB: {file_path}")


if __name__ == "__main__":
    create_chroma_db()
