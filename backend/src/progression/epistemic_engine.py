
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from shared.contracts.errors import ContractValidationError, ResourceNotFoundError
from shared.contracts.game_state import GameState
from src.case_engine import CaseEngine

from .authorization import AuthorizationService
from .evidence_reactions import ResolvedReaction
from .epistemic_models import NpcBelief
from .knowledge import NpcKnowledge


__all__ = ["RevealDecision", "AuthorizedKnowledge", "EpistemicEngine"]


@dataclass(frozen=True, slots=True)
class RevealDecision:
    """Explain whether an NPC may disclose one fact in the current turn."""

    suspect_id: str
    fact_id: str
    allowed: bool
    reason: str
    via_clue_id: str | None = None
    is_secret: bool = False


@dataclass(frozen=True, slots=True)
class AuthorizedKnowledge:
    """NPC knowledge separated from facts safe to use in dialogue context."""

    suspect_id: str
    stage_id: str
    known_fact_ids: tuple[str, ...]
    secret_fact_ids: tuple[str, ...]
    available_fact_ids: tuple[str, ...]
    revealable_fact_ids: tuple[str, ...]
    concealed_fact_ids: tuple[str, ...]
    belief_ids: tuple[str, ...]


class EpistemicEngine:
    """Deterministic NPC knowledge and disclosure boundary.

    AuthorizationService remains the source of player progression, stage and
    clue validation. This class distinguishes what an NPC knows, what is
    currently unlocked, and what the NPC may reveal in this dialogue turn.
    Beliefs are optional authored metadata and are never inferred from facts.
    """

    __slots__ = ("_authorization", "_engine", "_knowledge", "_beliefs")

    def __init__(
        self,
        authorization: AuthorizationService,
        knowledge: Mapping[str, NpcKnowledge],
        beliefs: Mapping[str, tuple[NpcBelief, ...]] | None = None,
    ) -> None:
        if not isinstance(authorization, AuthorizationService):
            raise TypeError("'authorization' must be an AuthorizationService.")
        engine = authorization.engine
        if not isinstance(knowledge, Mapping):
            raise TypeError("'knowledge' must be a mapping.")

        expected = set(engine.case.suspect_ids)
        problems: list[str] = []
        missing = sorted(expected - set(knowledge))
        extra = sorted(set(knowledge) - expected)

        if missing:
            problems.append(f"missing NPC knowledge: {', '.join(missing)}")
        if extra:
            problems.append(f"unknown NPC knowledge entries: {', '.join(extra)}")

        for suspect_id, entry in knowledge.items():
            if not isinstance(entry, NpcKnowledge):
                problems.append(f"{suspect_id!r} must map to NpcKnowledge.")
            elif entry.suspect_id != suspect_id:
                problems.append(
                    f"knowledge key {suspect_id!r} does not match "
                    f"entry suspect_id {entry.suspect_id!r}."
                )

        if problems:
            raise ContractValidationError(
                "NPC knowledge does not match the loaded case.",
                details=tuple(problems),
                code="EPISTEMIC_KNOWLEDGE_INVALID",
            )

        normalized: dict[str, tuple[NpcBelief, ...]] = {
            suspect_id: () for suspect_id in engine.case.suspect_ids
        }

        if beliefs is not None:
            if not isinstance(beliefs, Mapping):
                raise TypeError("'beliefs' must be a mapping.")

            unknown_owners = sorted(set(beliefs) - expected)
            if unknown_owners:
                raise ContractValidationError(
                    "Beliefs reference suspects outside this case.",
                    details=tuple(unknown_owners),
                    code="EPISTEMIC_BELIEF_INVALID",
                )

            for suspect_id, entries in beliefs.items():
                if not isinstance(entries, tuple):
                    raise TypeError(
                        f"beliefs[{suspect_id!r}] must be a tuple."
                    )

                seen: set[str] = set()

                for index, belief in enumerate(entries):
                    if not isinstance(belief, NpcBelief):
                        raise TypeError(
                            f"beliefs[{suspect_id!r}][{index}] must be NpcBelief."
                        )

                    if belief.suspect_id != suspect_id:
                        problems.append(
                            f"belief {belief.belief_id!r} belongs to "
                            f"{belief.suspect_id!r}, not {suspect_id!r}."
                        )

                    if belief.belief_id in seen:
                        problems.append(
                            f"duplicate belief_id {belief.belief_id!r}."
                        )

                    seen.add(belief.belief_id)

                    if (
                        belief.target_fact_id is not None
                        and not engine.case.has_fact(belief.target_fact_id)
                    ):
                        problems.append(
                            f"belief {belief.belief_id!r} has unknown target "
                            f"fact {belief.target_fact_id!r}."
                        )

                    for fact_id in belief.basis_fact_ids:
                        if not engine.case.has_fact(fact_id):
                            problems.append(
                                f"belief {belief.belief_id!r} has unknown basis "
                                f"fact {fact_id!r}."
                            )

                normalized[suspect_id] = entries

        if problems:
            raise ContractValidationError(
                "NPC beliefs do not match the loaded case.",
                details=tuple(problems),
                code="EPISTEMIC_BELIEF_INVALID",
            )

        self._authorization = authorization
        self._engine = engine
        self._knowledge = MappingProxyType(dict(knowledge))
        self._beliefs = MappingProxyType(normalized)

    @property
    def engine(self) -> CaseEngine:
        return self._engine

    def get_npc_knowledge(self, suspect_id: str) -> NpcKnowledge:
        self._check_suspect(suspect_id)
        return self._knowledge[suspect_id]

    def get_npc_beliefs(self, suspect_id: str) -> tuple[NpcBelief, ...]:
        self._check_suspect(suspect_id)
        return self._beliefs[suspect_id]

    def can_npc_know(self, suspect_id: str, fact_id: str) -> bool:
        """True only when case data explicitly lists the fact as known or secret."""
        self._check_suspect(suspect_id)
        self._check_fact(fact_id)
        return fact_id in self._knowledge[suspect_id].permitted_fact_ids

    def can_npc_reveal(
        self,
        state: GameState,
        suspect_id: str,
        fact_id: str,
        presented_clue_ids: Iterable[str] = (),
    ) -> RevealDecision:
        """Check disclosure permission for this exact state and evidence turn.

        Ordinary known facts may be revealed once player-unlocked. Secret facts
        need an applicable evidence reaction that explicitly releases them.
        """
        self._authorization.validate_state(state)
        self._check_suspect(suspect_id)
        self._check_fact(fact_id)

        entry = self._knowledge[suspect_id]
        secret = fact_id in entry.secret_fact_ids

        if fact_id not in entry.permitted_fact_ids:
            return RevealDecision(
                suspect_id,
                fact_id,
                False,
                "The case data does not assign this fact to the suspect.",
            )

        fact_auth = self._authorization.authorize_facts(state, suspect_id)

        if fact_id not in fact_auth.authorized_fact_ids:
            return RevealDecision(
                suspect_id,
                fact_id,
                False,
                "The fact is not unlocked for the player in the current state.",
                is_secret=secret,
            )

        if not secret:
            return RevealDecision(
                suspect_id,
                fact_id,
                True,
                "The suspect knows this fact and it is unlocked for the player.",
            )

        reactions = self._authorization.resolve_evidence_reactions(
            state, suspect_id, presented_clue_ids
        )

        for reaction in reactions:
            if fact_id in reaction.reveal_fact_ids:
                return RevealDecision(
                    suspect_id,
                    fact_id,
                    True,
                    "A valid evidence reaction explicitly releases this secret.",
                    via_clue_id=reaction.clue_id,
                    is_secret=True,
                )

        return RevealDecision(
            suspect_id,
            fact_id,
            False,
            "The fact is secret and no applicable evidence reaction releases it.",
            is_secret=True,
        )

    def get_authorized_knowledge(
        self,
        state: GameState,
        suspect_id: str,
        presented_clue_ids: Iterable[str] = (),
    ) -> AuthorizedKnowledge:
        """Return the knowledge boundary for one dialogue turn.

        Owner 4 should pass only ``revealable_fact_ids`` as factual context to
        dialogue generation. ``available_fact_ids`` can still contain secrets.
        """
        self._authorization.validate_state(state)
        self._check_suspect(suspect_id)

        presented = tuple(presented_clue_ids)
        fact_auth = self._authorization.authorize_facts(state, suspect_id)

        reactions: tuple[ResolvedReaction, ...] = (
            self._authorization.resolve_evidence_reactions(
                state, suspect_id, presented
            )
            if presented
            else ()
        )

        entry = self._knowledge[suspect_id]
        available = set(fact_auth.authorized_fact_ids)
        secret_ids = set(entry.secret_fact_ids)

        released = {
            fact_id
            for reaction in reactions
            for fact_id in reaction.reveal_fact_ids
        }

        revealable = (available - secret_ids) | released
        concealed = (available & secret_ids) - released

        return AuthorizedKnowledge(
            suspect_id=suspect_id,
            stage_id=fact_auth.stage_id,
            known_fact_ids=entry.known_fact_ids,
            secret_fact_ids=entry.secret_fact_ids,
            available_fact_ids=fact_auth.authorized_fact_ids,
            revealable_fact_ids=tuple(
                fact_id
                for fact_id in fact_auth.authorized_fact_ids
                if fact_id in revealable
            ),
            concealed_fact_ids=tuple(
                fact_id
                for fact_id in fact_auth.authorized_fact_ids
                if fact_id in concealed
            ),
            belief_ids=tuple(
                belief.belief_id for belief in self._beliefs[suspect_id]
            ),
        )

    def _check_suspect(self, suspect_id: str) -> None:
        if not isinstance(suspect_id, str) or not suspect_id.strip():
            raise ValueError("'suspect_id' must be a non-empty string.")

        if not self._engine.case.has_suspect(suspect_id):
            raise ResourceNotFoundError(
                f"Unknown suspect id: {suspect_id!r}.",
                details=(f"case_id={self._engine.case_id}",),
                code="EPISTEMIC_SUSPECT_UNKNOWN",
            )

    def _check_fact(self, fact_id: str) -> None:
        if not isinstance(fact_id, str) or not fact_id.strip():
            raise ValueError("'fact_id' must be a non-empty string.")

        if not self._engine.case.has_fact(fact_id):
            raise ResourceNotFoundError(
                f"Unknown fact id: {fact_id!r}.",
                details=(f"case_id={self._engine.case_id}",),
                code="EPISTEMIC_FACT_UNKNOWN",
            )
