import re
from typing import List
from app.schemas.chat import CitationItem
from app.rag.vector_store import ScoredChunk


def build_citation_items(chunks: List[ScoredChunk]) -> List[CitationItem]:
    """Convert retrieved ScoredChunks into structured CitationItems for frontend highlighting."""
    citations: List[CitationItem] = []
    for idx, c in enumerate(chunks, start=1):
        filename = c.metadata.get("filename", "Document")
        page = c.metadata.get("page_number")
        section = c.metadata.get("section_name")

        # Preserve the complete chunk for the source passage drawer.
        raw_text = c.content.strip().replace("\n", " ")
        snippet = raw_text

        citations.append(
            CitationItem(
                citation_id=idx,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=filename,
                page_number=page,
                section_name=section,
                snippet=snippet,
                score=round(float(c.score), 4),
            )
        )
    return citations


def extract_cited_indices(answer_text: str) -> List[int]:
    """Extract which citation numbers like [1], [2] actually appear in the assistant's answer."""
    matches = re.findall(r"\[(\d+)\]", answer_text)
    return sorted(list(set(int(m) for m in matches)))
