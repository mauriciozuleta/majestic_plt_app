"""Feeds the uploaded knowledge-base documents (a business plan, say) into
the AI generators as their basis. Only source='upload' documents are used —
the generated reports mirrored into the knowledge base are outputs of these
generators, and feeding them back in as inputs would let one analysis
quietly become the "source" of the next.
"""

from sqlalchemy.orm import Session

from .. import models
from . import rag

# Enough of the plan to steer the analysis without crowding out the
# instructions and the live web research the generators are also doing.
MAX_CONTEXT_CHARS = 9000
MAX_CHUNKS = 8
GENERIC_QUERY = 'business plan strategy products customers markets export import operations growth'


def uploaded_knowledge_documents(db: Session) -> list[models.KnowledgeDocument]:
    return db.query(models.KnowledgeDocument).filter_by(in_knowledge_base=True, source='upload').all()


def business_context(db: Session, topic: str) -> tuple[str, list[str]]:
    """(context text, names of the documents it came from) most relevant to
    `topic` (e.g. a country name). Country-specific passages first, then the
    plan's general strategy passages so there's always a baseline even when
    the topic itself is barely mentioned. Empty when nothing is uploaded."""
    documents = uploaded_knowledge_documents(db)
    if not documents:
        return '', []

    doc_ids = [document.id for document in documents]
    hits = rag.search(doc_ids, f'{topic} {topic}', MAX_CHUNKS)
    seen = {(hit['doc_id'], hit['chunk_index']) for hit in hits}
    for hit in rag.search(doc_ids, GENERIC_QUERY, MAX_CHUNKS):
        if len(hits) >= MAX_CHUNKS:
            break
        if (hit['doc_id'], hit['chunk_index']) not in seen:
            hits.append(hit)
            seen.add((hit['doc_id'], hit['chunk_index']))

    blocks, used_names, total = [], [], 0
    for hit in hits:
        if total + len(hit['text']) > MAX_CONTEXT_CHARS:
            break
        blocks.append(f'[{hit["doc_name"]}]\n{hit["text"]}')
        total += len(hit['text'])
        if hit['doc_name'] not in used_names:
            used_names.append(hit['doc_name'])
    return '\n\n'.join(blocks), used_names


def context_prompt_section(context: str) -> str:
    if not context:
        return ''
    return f"""

These are our own internal documents (for example our business plan). Treat them as the authoritative \
description of who we are, what we sell, and where we want to operate, and write this from that point of view — \
emphasize what matters for our actual plans, and do not contradict them. They are our own material, not an \
external source, so don't cite them as a source for tariffs, taxes or regulations (those still need real, cited, \
current sources).

Our documents:
---
{context}
---
"""
