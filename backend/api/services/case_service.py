"""Session-less, public case information."""

from __future__ import annotations

from ..presenters import (
    present_clue_summary,
    present_fact,
    present_event,
    present_suspect,
)
from ..schemas.responses import (
    CaseDetail,
    CaseSummary,
    ClueSummary,
    FactPublic,
    SuspectPublic,
    TimelineEventPublic,
)
from .runtime import RuntimeRegistry

__all__ = ["CaseService"]


class CaseService:
    def __init__(self, registry: RuntimeRegistry) -> None:
        self._registry = registry

    def list_cases(self) -> list[CaseSummary]:
        return [
            CaseSummary(case_id=rt.case_id, title=rt.engine.case.title, playable=True)
            for rt in self._registry.all()
        ]

    def get_case(self, case_id: str) -> CaseDetail:
        runtime = self._registry.get(case_id)
        case = runtime.engine.case
        return CaseDetail(
            case_id=case.case_id,
            title=case.title,
            playable=True,
            description=case.description,
            suspect_count=len(case.suspect_ids),
        )

    def list_suspects(self, case_id: str) -> list[SuspectPublic]:
        runtime = self._registry.get(case_id)
        return [present_suspect(s) for s in runtime.engine.list_suspects()]

    def list_clues(self, case_id: str) -> list[ClueSummary]:
        """Clues that can be collected before any investigation (title and place only)."""
        runtime = self._registry.get(case_id)
        return [
            present_clue_summary(runtime.engine.get_clue(clue_id))
            for clue_id in runtime.public.clue_ids
        ]

    def list_facts(self, case_id: str) -> list[FactPublic]:
        """Baseline background facts only. Evidence- or stage-gated facts are never listed."""
        runtime = self._registry.get(case_id)
        return [present_fact(runtime.engine.get_fact(f)) for f in runtime.public.fact_ids]

    def list_timeline(self, case_id: str) -> list[TimelineEventPublic]:
        """Public backstory events, in the case file's declared order (NOT a chronology)."""
        runtime = self._registry.get(case_id)
        return [
            present_event(runtime, runtime.engine.get_timeline_event(e))
            for e in runtime.public.event_ids
        ]
