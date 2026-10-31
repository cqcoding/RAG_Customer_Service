from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="rag_customer_service",
    version="0.1.0",
    author="cqcoding",
    description="RAG System for Customer Service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/cqcoding/RAG_Customer_Service",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "langchain>=1.2.9",
        "langchain-community>=0.4.1",
        "langchain-core>=1.2.9",
        "langgraph>=1.0.8",
        "openai>=2.17.0",
        "tiktoken>=0.12.0",
        "chromadb>=1.5.0",
        "pypdf>=6.7.0",
        "python-docx>=1.2.0",
        "openpyxl>=3.1.5",
        "pandas>=2.3.3",
        "autogen-agentchat>=0.7.5",
        "python-dotenv>=1.2.1",
        "pydantic>=2.12.5",
        "requests>=2.32.5",
        "fastapi>=0.128.5",
        "uvicorn>=0.40.0",
        "streamlit>=1.54.0",
    ],
    extras_require={
        "dev": [
            "pytest>=9.0.2",
            "pytest-asyncio>=1.3.0",
            "black",
            "flake8",
            "mypy",
        ],
    },
)