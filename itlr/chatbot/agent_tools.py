"""Bounded, read-only tool execution for the evidence stage."""
from __future__ import annotations

from contextvars import ContextVar
import logging
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from itlr.observability.tracing import span

request_id: ContextVar[str | None] = ContextVar('itlr_request_id', default=None)
logger = logging.getLogger(__name__)


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')

    query: str = Field(max_length=6000)
    top_k: int = Field(ge=1, le=32)
    item_type: str | None = Field(default=None, max_length=50)


class SearchHit(BaseModel):
    chunk_id: str = Field(pattern=r'^\d+:\d+$')
    excerpt: str = Field(min_length=1)
    dense_score: float = Field(ge=-1., le=1.)
    item: dict

    @model_validator(mode='after')
    def validate_owner(self):
        if self.item.get('item_id') != int(self.chunk_id.split(':', 1)[0]):
            raise ValueError('Chunk owner does not match item')
        return self


search_hits = TypeAdapter(list[SearchHit])
TOOL_SCHEMAS = {
    'search_knowledge': {
        'input': SearchArguments.model_json_schema(),
        'output': search_hits.json_schema(),
    },
}


class KnowledgeSearch:
    """The server's retrieval plan can search a type and then retry unfiltered."""

    def __init__(self, retrieval):
        self.retrieval = retrieval
        self.remaining = 2
        self.correlation_id = request_id.get() or uuid4().hex

    def search(self, query, *, top_k=8, item_type=None, vector=None):
        args = SearchArguments(query=query, top_k=top_k, item_type=item_type)
        if self.remaining == 0:
            raise RuntimeError('Knowledge search step limit reached')
        self.remaining -= 1
        started = perf_counter()
        outcome = 'error'
        try:
            with span('agent.search_knowledge'):
                hits = self.retrieval.search(args.query, top_k=args.top_k, item_type=args.item_type,
                                             vector=vector)
                search_hits.validate_python(hits)
                if len(hits) > args.top_k:
                    raise ValueError('Tool returned too many search hits')
                outcome = 'ok'
                return hits
        finally:
            logger.debug('agent tool=search_knowledge request_id=%s outcome=%s elapsed_ms=%.1f',
                         self.correlation_id, outcome, (perf_counter() - started) * 1000)
