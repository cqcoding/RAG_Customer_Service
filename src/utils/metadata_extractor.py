"""
Metadata extraction utilities for financial documents.
"""
import re
from pathlib import Path
from typing import Dict, Optional

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def extract_metadata_from_html(file_path: str, content: str) -> Dict[str, str]:
    metadata = {
        "source": file_path,
        "file_type": "html"
    }
    
    # Extract from filename (e.g., tsla-20231231.html)
    filename = Path(file_path).stem
    
    # Extract ticker symbol from filename
    ticker_match = re.match(r'^([a-zA-Z]+)', filename)
    if ticker_match:
        metadata["ticker"] = ticker_match.group(1).upper()
    
    # Extract date from filename
    date_match = re.search(r'(\d{8})', filename)
    if date_match:
        date_str = date_match.group(1)
        metadata["filing_date"] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        metadata["fiscal_year"] = date_str[:4]
        metadata["fiscal_period"] = f"FY{date_str[:4]}"
    
    # Parse HTML content for additional metadata
    try:
        if HAS_BS4:
            soup = BeautifulSoup(content, 'html.parser')
            text_content = soup.get_text()
        else:
            # Simple HTML stripping without BeautifulSoup
            text_content = re.sub(r'<[^>]+>', ' ', content)
            text_content = re.sub(r'\s+', ' ', text_content)
        
        # Check for form types
        if re.search(r'FORM\s*10-K', text_content, re.IGNORECASE):
            metadata["document_type"] = "10-K"
            metadata["doc_category"] = "Annual Report"
        elif re.search(r'FORM\s*10-Q', text_content, re.IGNORECASE):
            metadata["document_type"] = "10-Q"
            metadata["doc_category"] = "Quarterly Report"
        elif re.search(r'FORM\s*8-K', text_content, re.IGNORECASE):
            metadata["document_type"] = "8-K"
            metadata["doc_category"] = "Current Report"
        elif re.search(r'ANNUAL\s*REPORT', text_content, re.IGNORECASE):
            metadata["document_type"] = "Annual Report"
            metadata["doc_category"] = "Annual Report"
        
        # Extract company name from document
        company_patterns = [
            r'([\w\s&.,]+)\s*\(?[Tt]icker[:\s]*[A-Z]+\)?',
            r'UNITED STATES.*?COMMISSION.*?\n\n([A-Z][A-Za-z\s&.,]+)\n',
        ]
        
        for pattern in company_patterns:
            company_match = re.search(pattern, text_content[:2000])
            if company_match:
                company_name = company_match.group(1).strip()
                if len(company_name) < 50:  # Reasonable company name length
                    metadata["company_name"] = company_name
                    break
        
        # Look for fiscal year mentions
        fy_match = re.search(r'fiscal year ended?\s*(?:December|January|February|March|April|May|June|July|August|September|October|November)\s+\d{1,2},?\s+(\d{4})', text_content, re.IGNORECASE)
        if fy_match:
            metadata["fiscal_year_end"] = fy_match.group(1)
            
    except Exception as e:
        # If parsing fails, we still have basic metadata from filename
        metadata["parsing_error"] = str(e)
    
    return metadata


def extract_metadata_from_pdf(file_path: str) -> Dict[str, str]:
    metadata = {
        "source": file_path,
        "file_type": "pdf"
    }
    
    # Extract from filename
    filename = Path(file_path).stem
    
    # Extract ticker if present
    ticker_match = re.match(r'^([a-zA-Z]+)', filename)
    if ticker_match:
        metadata["ticker"] = ticker_match.group(1).upper()
    
    # Extract date patterns
    date_match = re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})', filename)
    if date_match:
        metadata["filing_date"] = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
        metadata["fiscal_year"] = date_match.group(1)
    
    return metadata


def extract_metadata_from_txt(file_path: str, content: str) -> Dict[str, str]:
    metadata = {
        "source": file_path,
        "file_type": "txt"
    }
    
    # Extract from filename
    filename = Path(file_path).stem
    
    # Extract ticker if present
    ticker_match = re.match(r'^([a-zA-Z]+)', filename)
    if ticker_match:
        metadata["ticker"] = ticker_match.group(1).upper()
    
    # Look for document type in content
    if re.search(r'10-K', content[:500], re.IGNORECASE):
        metadata["document_type"] = "10-K"
    elif re.search(r'10-Q', content[:500], re.IGNORECASE):
        metadata["document_type"] = "10-Q"
    
    return metadata
