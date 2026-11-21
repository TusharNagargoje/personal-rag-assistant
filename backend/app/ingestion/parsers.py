import re
from typing import List, Optional
from app.core.logging import logger


class ParsedPage:
    def __init__(self, content: str, page_number: Optional[int] = None, section: Optional[str] = None):
        self.content = content
        self.page_number = page_number
        self.section = section


def parse_pdf(file_path: str) -> List[ParsedPage]:
    """Parse PDF with PyMuPDF, falling back to pypdf or OCR if page is image-only."""
    pages = []
    # Primary: PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(file_path)
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_text("text").strip()
            # If text is empty, check for OCR fallback if pytesseract installed
            if not text:
                try:
                    import pytesseract
                    from PIL import Image
                    import io
                    pix = page.get_pixmap()
                    img = Image.open(io.BytesIO(pix.tobytes()))
                    text = pytesseract.image_to_string(img).strip()
                except Exception as ocr_err:
                    logger.debug(f"OCR fallback skipped or failed: {ocr_err}")
            if text:
                pages.append(ParsedPage(content=text, page_number=page_idx + 1))
        doc.close()
        if pages:
            return pages
    except Exception as e:
        logger.warning(f"PyMuPDF failed, falling back to pypdf: {e}")

    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(ParsedPage(content=text, page_number=idx + 1))
    except Exception as e:
        logger.error(f"pypdf extraction error: {e}")
        raise ValueError(f"Failed to parse PDF document: {str(e)}")

    return pages


def parse_docx(file_path: str) -> List[ParsedPage]:
    """Parse Microsoft Word DOCX files preserving heading sections."""
    try:
        import docx
        doc = docx.Document(file_path)
        sections = []
        current_section = "Main"
        current_text = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            if p.style and p.style.name.startswith("Heading"):
                if current_text:
                    sections.append(ParsedPage(content="\n".join(current_text), section=current_section))
                    current_text = []
                current_section = text
            current_text.append(text)

        if current_text:
            sections.append(ParsedPage(content="\n".join(current_text), section=current_section))

        # Also extract tables
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    table_rows.append(row_text)
            if table_rows:
                sections.append(ParsedPage(content="\n".join(table_rows), section="Table Data"))

        return sections
    except Exception as e:
        logger.error(f"DOCX parsing error: {e}")
        raise ValueError(f"Failed to parse DOCX file: {str(e)}")


def parse_text_or_markdown(file_path: str) -> List[ParsedPage]:
    """Parse TXT or Markdown files."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Split markdown by top-level headers (# or ##) if present
        if file_path.endswith((".md", ".markdown")):
            header_splits = re.split(r"(?m)^(?=#{1,3}\s+)", content)
            pages = []
            for chunk in header_splits:
                chunk = chunk.strip()
                if chunk:
                    first_line = chunk.split("\n")[0].replace("#", "").strip()
                    pages.append(ParsedPage(content=chunk, section=first_line[:64]))
            if pages:
                return pages

        return [ParsedPage(content=content.strip())]
    except Exception as e:
        logger.error(f"Text/Markdown parsing error: {e}")
        raise ValueError(f"Failed to parse text file: {str(e)}")


def parse_tabular(file_path: str) -> List[ParsedPage]:
    """Parse CSV or Excel (XLSX/XLS) files."""
    try:
        import pandas as pd
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Batch rows into groups of 25 for meaningful context chunks
        pages = []
        batch_size = 25
        num_rows = len(df)
        headers = ", ".join(str(c) for c in df.columns)

        for i in range(0, num_rows, batch_size):
            batch_df = df.iloc[i : i + batch_size]
            row_texts = []
            for _, row in batch_df.iterrows():
                row_str = "; ".join(f"{col}: {val}" for col, val in row.items() if pd.notna(val))
                row_texts.append(row_str)

            chunk_content = f"Columns: {headers}\nRows {i+1} to {min(i+batch_size, num_rows)}:\n" + "\n".join(row_texts)
            pages.append(ParsedPage(content=chunk_content, section=f"Rows {i+1}-{min(i+batch_size, num_rows)}"))

        return pages
    except Exception as e:
        logger.error(f"Tabular parsing error: {e}")
        raise ValueError(f"Failed to parse CSV/Excel file: {str(e)}")


def parse_pptx(file_path: str) -> List[ParsedPage]:
    """Parse PowerPoint PPTX presentation slides."""
    try:
        from pptx import Presentation
        prs = Presentation(file_path)
        pages = []
        for idx, slide in enumerate(prs.slides):
            slide_texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = paragraph.text.strip()
                        if text:
                            slide_texts.append(text)
            # Notes slide text
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    slide_texts.append(f"Notes: {notes}")

            if slide_texts:
                pages.append(ParsedPage(content="\n".join(slide_texts), page_number=idx + 1, section=f"Slide {idx + 1}"))

        return pages
    except Exception as e:
        logger.error(f"PPTX parsing error: {e}")
        raise ValueError(f"Failed to parse PPTX file: {str(e)}")


def parse_web_url(url: str) -> List[ParsedPage]:
    """Scrape and extract main body content from a web page."""
    try:
        from app.core.guardrails import validate_public_http_url
        is_valid, reason = validate_public_http_url(url)
        if not is_valid:
            raise ValueError(reason)
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        # Do not automatically follow redirects: validate each target before
        # requesting it so ingestion cannot become an SSRF proxy.
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=False)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else url
        body = soup.get_text(separator="\n")
        # Clean consecutive newlines
        cleaned_text = re.sub(r"\n\s*\n+", "\n\n", body).strip()

        return [ParsedPage(content=f"Source URL: {url}\nTitle: {title}\n\n{cleaned_text}", section=title[:100])]
    except Exception as e:
        logger.error(f"Web URL scraping error for {url}: {e}")
        raise ValueError(f"Failed to scrape webpage: {str(e)}")


def parse_youtube_transcript(url: str) -> List[ParsedPage]:
    """Extract subtitles transcript from YouTube video URL."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Extract video ID from common URL formats
        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id_match:
            raise ValueError("Invalid YouTube URL: could not find video ID.")
        video_id = video_id_match.group(1)

        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            transcript = api.fetch(video_id)
            entries = transcript.to_raw_data() if hasattr(transcript, "to_raw_data") else transcript
        else:  # compatibility with youtube-transcript-api < 1.0
            entries = YouTubeTranscriptApi.get_transcript(video_id)
        # Group into ~2 minute segments
        pages = []
        current_segment = []
        current_time = 0

        for entry in entries:
            start_sec = int(entry.get("start", 0) if isinstance(entry, dict) else getattr(entry, "start", 0))
            text = (entry.get("text", "") if isinstance(entry, dict) else getattr(entry, "text", "")).strip()
            if not text:
                continue
            current_segment.append(text)
            if start_sec - current_time >= 120:  # 2 minutes
                min_start = current_time // 60
                sec_start = current_time % 60
                pages.append(ParsedPage(
                    content=f"[{min_start:02d}:{sec_start:02d}] " + " ".join(current_segment),
                    section=f"Timestamp {min_start:02d}:{sec_start:02d}"
                ))
                current_segment = []
                current_time = start_sec

        if current_segment:
            min_start = current_time // 60
            sec_start = current_time % 60
            pages.append(ParsedPage(
                content=f"[{min_start:02d}:{sec_start:02d}] " + " ".join(current_segment),
                section=f"Timestamp {min_start:02d}:{sec_start:02d}"
            ))

        return pages
    except Exception as e:
        logger.error(f"YouTube transcript extraction error: {e}")
        raise ValueError(f"Failed to extract YouTube transcript: {str(e)}")


def parse_document(file_path: str, file_type: str) -> List[ParsedPage]:
    """Route document parsing based on file type."""
    ext = file_type.lower()
    if ext == "pdf":
        return parse_pdf(file_path)
    elif ext in ["docx", "doc"]:
        return parse_docx(file_path)
    elif ext in ["txt", "md", "markdown"]:
        return parse_text_or_markdown(file_path)
    elif ext in ["csv", "xlsx", "xls"]:
        return parse_tabular(file_path)
    elif ext in ["pptx", "ppt"]:
        return parse_pptx(file_path)
    elif ext == "url":
        return parse_web_url(file_path)
    elif ext == "youtube":
        return parse_youtube_transcript(file_path)
    else:
        # Default try plain text
        return parse_text_or_markdown(file_path)
