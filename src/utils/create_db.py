from langchain_chroma import Chroma
from langchain_text_splitters import NLTKTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.document_loaders import CSVLoader, DirectoryLoader, TextLoader, PyPDFLoader, UnstructuredHTMLLoader
from dotenv import load_dotenv
from src.config import get_settings
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from src.utils.metadata_extractor import extract_metadata_from_html, extract_metadata_from_pdf, extract_metadata_from_txt
from pathlib import Path


load_dotenv()
DATA_PATH = Path(__file__).resolve().parents[2] / "data"

def loaders():
    pdf_loader = DirectoryLoader(
        str(DATA_PATH), 
        glob='**/*.pdf', 
        loader_cls=PyPDFLoader)
    csv_loader = DirectoryLoader(
        str(DATA_PATH), 
        glob='**/*.csv', 
        loader_cls=TextLoader)

    return pdf_loader, csv_loader


def enrich_documents_with_metadata(documents):
    enriched_docs = []
    
    for doc in documents:
        source_path = doc.metadata.get('source', '')
        file_extension = Path(source_path).suffix.lower()
        
        # Extract metadata based on file type
        if file_extension == '.pdf':
            additional_metadata = extract_metadata_from_pdf(source_path)
        elif file_extension == '.txt':
            additional_metadata = extract_metadata_from_txt(source_path, doc.page_content)
        else:
            additional_metadata = {}
        
        doc.metadata.update(additional_metadata)
        enriched_docs.append(doc)
    
    return enriched_docs

def create_chroma_db():
    settings = get_settings()
    
    # Initialize the embedding model
    embed_model = FastEmbedEmbeddings(
        model_name="BAAI/bge-base-en-v1.5"
        )

    # Load all document types
    documents = []
    pdf_loader, csv_loader = loaders()
    documents.extend(pdf_loader.load())
    documents.extend(csv_loader.load())
    
    # Add metadata to docs
    documents = enrich_documents_with_metadata(documents)
    print(f"Sample metadata: {documents[0].metadata if documents else 'No documents'}")

    # Hybrid chunking
    sentence_splitter = NLTKTextSplitter()
    sentences = sentence_splitter.split_documents(documents)

    chunker = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=80
    )

    chunks = chunker.split_documents(sentences)

    sizes = [len(c.page_content) for c in chunks]

    print("Docs:", len(documents))
    print("Sentences:", len(sentences))
    print("Chunks:", len(chunks))
    print("Chunk size — min / avg / max:",
        min(sizes),
        sum(sizes)//len(sizes),
        max(sizes))
    
    # Create and populate the Chroma vector store
    chroma_db = Chroma(
        collection_name='my_collection',
        embedding_function=embed_model,
        persist_directory=settings.chroma_db_path
    )

    batch_size = 25

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        chroma_db.add_documents(batch)

    print(f"Chroma DB created at {settings.chroma_db_path}")


def add_file_to_chroma_db(file_path: str) -> None:
    settings = get_settings()

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Initialize the embedding model
    embed_model = FastEmbedEmbeddings(
        model_name="BAAI/bge-base-en-v1.5"
    )

    # Load document based on extension
    file_extension = path.suffix.lower()
    if file_extension == ".pdf":
        loader = PyPDFLoader(str(path))
    elif file_extension == ".csv":
        loader = CSVLoader(str(path))
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")

    documents = loader.load()

    # Add metadata to docs
    documents = enrich_documents_with_metadata(documents)

    # Hybrid chunking
    sentence_splitter = NLTKTextSplitter()
    sentences = sentence_splitter.split_documents(documents)

    chunker = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=80
    )

    chunks = chunker.split_documents(sentences)

    chroma_db = Chroma(
        collection_name='my_collection',
        embedding_function=embed_model,
        persist_directory=settings.chroma_db_path
    )

    batch_size = 25
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        chroma_db.add_documents(batch)

    print(f"Added file to Chroma DB: {file_path}")


if __name__ == '__main__':
    create_chroma_db()