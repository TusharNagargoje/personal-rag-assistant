from typing import List, Dict, Any, Optional
from app.ingestion.parsers import ParsedPage
from app.core.config import settings


class TextChunk:
    def __init__(
        self,
        content: str,
        chunk_index: int,
        page_number: Optional[int] = None,
        section_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.content = content
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.section_name = section_name
        self.metadata = metadata or {}


def recursive_split_text(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
    separators: Optional[List[str]] = None,
) -> List[str]:
    """Hierarchical text splitter that respects paragraph and sentence boundaries."""
    if separators is None:
        separators = ["\n\n", "\n", ". ", "; ", ", ", " "]

    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    # Find the first separator that exists in the text
    chosen_sep = ""
    for sep in separators:
        if sep in text:
            chosen_sep = sep
            break

    if not chosen_sep:
        # Fallback to character slicing
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + chunk_size])
            start += chunk_size - chunk_overlap
        return chunks

    splits = text.split(chosen_sep)
    docs = []
    current_doc = []
    total_len = 0

    for piece in splits:
        piece_len = len(piece)
        if total_len + piece_len + len(chosen_sep) > chunk_size and current_doc:
            doc_str = chosen_sep.join(current_doc).strip()
            if doc_str:
                docs.append(doc_str)
            # Retain overlap from end of current_doc
            overlap_pieces = []
            overlap_len = 0
            for back_piece in reversed(current_doc):
                if overlap_len + len(back_piece) <= chunk_overlap:
                    overlap_pieces.insert(0, back_piece)
                    overlap_len += len(back_piece) + len(chosen_sep)
                else:
                    break
            current_doc = overlap_pieces
            total_len = overlap_len

        current_doc.append(piece)
        total_len += piece_len + len(chosen_sep)

    if current_doc:
        doc_str = chosen_sep.join(current_doc).strip()
        if doc_str:
            docs.append(doc_str)

    return docs


def chunk_parsed_pages(
    pages: List[ParsedPage],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[TextChunk]:
    """Convert parsed pages into indexed, metadata-rich TextChunks."""
    size = chunk_size or settings.DEFAULT_CHUNK_SIZE
    overlap = chunk_overlap or settings.DEFAULT_CHUNK_OVERLAP

    all_chunks: List[TextChunk] = []
    global_chunk_idx = 0

    for page in pages:
        raw_text = page.content.strip()
        if not raw_text:
            continue

        split_pieces = recursive_split_text(raw_text, chunk_size=size, chunk_overlap=overlap)
        for piece in split_pieces:
            chunk = TextChunk(
                content=piece,
                chunk_index=global_chunk_idx,
                page_number=page.page_number,
                section_name=page.section,
                metadata={
                    "char_count": len(piece),
                    "estimated_tokens": max(1, len(piece) // 4),
                },
            )
            all_chunks.append(chunk)
            global_chunk_idx += 1

    return all_chunks
