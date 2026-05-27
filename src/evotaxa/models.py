from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class Document:
    doc_id: str
    title: str
    text: str
    published_at: date | None = None
    chronology_slice: str = ""
    role: str = ""
    source_type: str = "document"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n".join(part for part in [self.title, self.text] if part).strip()

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["published_at"] = self.published_at.isoformat() if self.published_at else None
        return record


@dataclass
class DimensionSpec:
    dimension_id: str
    display_name: str
    definition: str = ""


@dataclass
class TaxonomyNode:
    node_id: str
    dimension: str
    canonical_label: str
    parent_id: str = ""
    definition: str = ""
    created_time_slice: str = ""
    aliases: list[str] = field(default_factory=list)
    support_documents: list[str] = field(default_factory=list)
    representative_documents: list[str] = field(default_factory=list)
    counterexample_documents: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NodeQuality:
    node_id: str
    dimension_alignment: float
    granularity: float
    sibling_coherence: float
    uniqueness: float
    paper_relevance: float
    coverage: float
    temporal_stability: float
    boundary_clarity: float
    judge_notes: str = ""

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionEntity:
    entity_id: str
    canonical_name: str
    aliases: list[str]
    first_seen_date: str
    support_documents: list[str]
    taxonomy_nodes: list[str]
    entity_type: str

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityMention:
    doc_id: str
    entity_id: str
    canonical_name: str
    taxonomy_nodes: list[str]
    evidence: str

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionEdge:
    edge_id: str
    source_entity: str
    target_entity: str
    edge_type: str
    source_document: str
    target_document: str
    time_delta_days: int | None
    taxonomy_nodes: list[str]
    confidence: float
    evidence: dict[str, Any]
    substring_verified: bool

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionChain:
    chain_id: str
    entity_path: list[str]
    edge_path: list[str]
    taxonomy_nodes: list[str]
    score: float

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

