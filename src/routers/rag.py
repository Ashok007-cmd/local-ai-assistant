from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.rag_index import rag_index

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag"])

class IndexDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=1000)
    content: str = Field(..., min_length=1, max_length=100_000)


class RAGSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)


@router.post("/api/rag/index")
async def index_document(req: IndexDocumentRequest):
    """Index a document asynchronously in the SQLite FTS5 index."""
    await rag_index.index_document_async(req.title, req.content)
    return {"success": True, "message": "Document indexed successfully"}


@router.delete("/api/rag/clear")
async def clear_rag_index():
    """Clear all documents from the FTS5 index asynchronously."""
    await rag_index.clear_async()
    return {"success": True, "message": "RAG index cleared"}


@router.post("/api/rag/search")
async def rag_search(req: RAGSearchRequest):
    """Search documents asynchronously in the SQLite FTS5 index."""
    doc_count = await rag_index.get_count_async()
    if doc_count == 0:
        return {
            "query": req.query,
            "results": [],
            "context": "No documents available"
        }

    results = await rag_index.search_documents_async(req.query)

    if results:
        context = "\n\n".join(res["document"]["content"] for res in results)
    else:
        context = "No relevant context found."

    return {
        "query": req.query,
        "results": results,
        "context": context
    }
