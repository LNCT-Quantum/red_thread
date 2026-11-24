"""Per-case runtime: the existing engine, progression gate, repository and state manager.

Nothing here re-implements game logic. It only wires the existing modules together the
way ``backend/src/game_state/readme.md`` prescribes (one shared ``CaseEngine`` for the
gate and the state manager) and decides which parts of a case are *public*.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from shared.contracts.errors import RedThreadError, ResourceNotFoundError
from shared.contracts.game_state import GameState
from src.case_engine import CaseEngine
from src.case_engine.loader import DEFAULT_DATA_ROOT
from src.game_state import GameStateManager, GameStateRepository, InMemoryGameStateRepository
from src.progression import ProgressionGate

from ..errors import ApiError

__all__ = ["PublicCaseView", "CaseRuntime", "RuntimeRegistry", "build_runtime"]

log = logging.getLogger("redthread.api.runtime")
_CASE_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class PublicCaseView:
    """What may be shown without a session, derived from the *existing* authorization rules.

    The progression gate's initial-state view is the definition of "baseline": facts that are
    not stage-gated, not clue-linked and not any suspect's secret, and clues that are unlocked
    before any investigation has happened. A timeline event is public only if every fact it
    relates to is public, so events describing the crime itself are never listed.
    """

    fact_ids: tuple[str, ...]
    clue_ids: tuple[str, ...]
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseRuntime:
    engine: CaseEngine
    gate: ProgressionGate
    repository: GameStateRepository
    manager: GameStateManager
    public: PublicCaseView

    @property
    def case_id(self) -> str:
        return self.engine.case_id


def _public_view(engine: CaseEngine, gate: ProgressionGate) -> PublicCaseView:
    preview = gate.manager.initial_state("public-preview")  # never stored
    fact_ids = gate.authorization.unlocked_fact_ids(preview)
    clue_ids = gate.authorization.unlocked_clue_ids(preview)
    public_facts = set(fact_ids)
    event_ids = tuple(
        event.timeline_event_id
        for event in engine.list_timeline_events()
        if event.related_fact_ids and set(event.related_fact_ids) <= public_facts
    )
    return PublicCaseView(fact_ids=fact_ids, clue_ids=clue_ids, event_ids=event_ids)


def build_runtime(case_id: str, data_root: Path | None = None) -> CaseRuntime:
    engine = CaseEngine.load(case_id, data_root)
    gate = ProgressionGate.from_engine(engine, data_root=data_root)
    repository = InMemoryGameStateRepository()  # NOT durable: sessions vanish on restart
    manager = GameStateManager(engine, repository, gate)
    return CaseRuntime(engine, gate, repository, manager, _public_view(engine, gate))


class RuntimeRegistry:
    """The set of playable cases, each with its own isolated session store."""

    def __init__(self, runtimes: Mapping[str, CaseRuntime], failed: Iterable[str] = ()) -> None:
        self._runtimes = dict(runtimes)
        self.failed_case_ids = tuple(failed)

    @classmethod
    def load(cls, case_ids: tuple[str, ...] | None, data_root: Path | None) -> RuntimeRegistry:
        root = data_root if data_root is not None else DEFAULT_DATA_ROOT
        if case_ids is None:
            candidates = sorted(
                entry.name
                for entry in root.iterdir()
                if entry.is_dir() and _CASE_DIR_RE.match(entry.name) and (entry / "case.json").is_file()
            ) if root.is_dir() else []
        else:
            candidates = list(case_ids)

        runtimes: dict[str, CaseRuntime] = {}
        failed: list[str] = []
        for case_id in candidates:
            try:
                runtimes[case_id] = build_runtime(case_id, data_root)
                log.info("loaded case %s", case_id)
            except (RedThreadError, OSError, ValueError, TypeError) as exc:
                # Filesystem paths and data details stay in the server log only.
                log.error("case %s failed to load: %s", case_id, exc)
                failed.append(case_id)
        return cls(runtimes, failed)

    def all(self) -> tuple[CaseRuntime, ...]:
        return tuple(self._runtimes.values())

    def get(self, case_id: str) -> CaseRuntime:
        runtime = self._runtimes.get(case_id)
        if runtime is None:
            raise ApiError(404, "CASE_NOT_FOUND", "The requested case does not exist")
        return runtime

    def find_session(self, session_id: str) -> tuple[CaseRuntime, GameState]:
        """Locate a session in whichever case store holds it."""
        for runtime in self._runtimes.values():
            try:
                return runtime, runtime.manager.get_game_state(session_id)
            except ResourceNotFoundError:
                continue
        raise ApiError(404, "SESSION_NOT_FOUND", "The requested session does not exist")
