import pytest

from shared.contracts.dialogue import DialogueRequest
from shared.contracts.errors import ContractValidationError
from src.progression.epistemic_models import BeliefStatus, NpcBelief

from shared.contracts.game_state import GameState
from src.case_engine import CaseEngine
from src.progression.authorization import AuthorizationService
from src.progression.epistemic_engine import EpistemicEngine
from src.progression.knowledge import load_npc_knowledge
from src.progression.progression_rules import load_progression_rules

@pytest.fixture
def setup_engine():
    case_engine = CaseEngine.load("case_001")
    knowledge = load_npc_knowledge(case_engine)
    rules = load_progression_rules(case_engine)

    authorization = AuthorizationService(
        case_engine,
        rules,
        knowledge,
    )

    epistemic = EpistemicEngine(
        authorization,
        knowledge,
    )

    state = GameState(
        game_id="test_game",
        case_id="case_001",
    )

    return epistemic, state

def make_stage_3_state():
    return GameState(
        game_id="test_game",
        case_id="case_001",
        discovered_clue_ids=(
            "clue_001",
            "clue_004",
            "clue_012",
            "clue_005",
            "clue_007",
            "clue_011",
            "clue_015",
        ),
        interviewed_suspect_ids=(
            "suspect_001",
            "suspect_002",
            "suspect_003",
        ),
        completed_objective_ids=(
            "stage:stage_2",
            "stage:stage_3",
        ),
    )


def make_stage_4_state():
    return GameState(
        game_id="test_game",
        case_id="case_001",
        discovered_clue_ids=(
            "clue_001",
            "clue_004",
            "clue_012",
            "clue_005",
            "clue_007",
            "clue_011",
            "clue_014",
            "clue_015",
            "clue_019",
            "clue_020",
        ),
        interviewed_suspect_ids=(
            "suspect_001",
            "suspect_002",
            "suspect_003",
        ),
        completed_objective_ids=(
            "stage:stage_2",
            "stage:stage_3",
            "stage:stage_4",
        ),
    )


def test_secret_fact_locked_before_stage_4(setup_engine):
    epistemic, _ = setup_engine
    state = make_stage_3_state()

    result = epistemic.get_authorized_knowledge(
        state,
        "suspect_002",
        presented_clue_ids=("clue_007",),
    )

    assert "fact_017" not in result.available_fact_ids
    assert "fact_028" not in result.available_fact_ids


def test_secret_fact_remains_concealed_at_stage_4(setup_engine):
    epistemic, _ = setup_engine
    state = make_stage_4_state()

    result = epistemic.get_authorized_knowledge(
        state,
        "suspect_002",
        presented_clue_ids=("clue_015",),
    )

    assert "fact_017" in result.available_fact_ids
    assert "fact_017" in result.concealed_fact_ids
    assert "fact_017" not in result.revealable_fact_ids


def test_evidence_reveals_fact_028_at_stage_4(setup_engine):
    epistemic, _ = setup_engine
    state = make_stage_4_state()

    decision = epistemic.can_npc_reveal(
        state,
        "suspect_002",
        "fact_028",
        presented_clue_ids=("clue_015",),
    )

    assert decision.allowed is True
    assert decision.via_clue_id == "clue_015"


def test_secret_fact_017_cannot_be_revealed_by_clue_015(setup_engine):
    epistemic, _ = setup_engine
    state = make_stage_4_state()

    decision = epistemic.can_npc_reveal(
        state,
        "suspect_002",
        "fact_017",
        presented_clue_ids=("clue_015",),
    )

    assert decision.allowed is False
    assert decision.is_secret is True


def test_evidence_does_not_reveal_secret_before_stage_4(setup_engine):
    epistemic, _ = setup_engine
    state = make_stage_3_state()

    decision = epistemic.can_npc_reveal(
        state,
        "suspect_002",
        "fact_028",
        presented_clue_ids=("clue_015",),
    )

    assert decision.allowed is False

def test_authored_belief_is_preserved(setup_engine):
    epistemic, _ = setup_engine

    belief = NpcBelief(
        belief_id="belief_001",
        suspect_id="suspect_001",
        proposition="The victim was hiding something.",
        status=BeliefStatus.SUSPECTS,
        confidence=0.7,
        target_fact_id="fact_001",
        basis_fact_ids=("fact_010",),
    )

    engine = EpistemicEngine(
        epistemic._authorization,
        {
            "suspect_001": epistemic.get_npc_knowledge("suspect_001"),
            "suspect_002": epistemic.get_npc_knowledge("suspect_002"),
            "suspect_003": epistemic.get_npc_knowledge("suspect_003"),
        },
        beliefs={"suspect_001": (belief,)},
    )

    assert engine.get_npc_beliefs("suspect_001") == (belief,)


def test_beliefs_are_separate_for_each_npc(setup_engine):
    epistemic, _ = setup_engine

    knowledge = {
        suspect_id: epistemic.get_npc_knowledge(suspect_id)
        for suspect_id in (
            "suspect_001",
            "suspect_002",
            "suspect_003",
        )
    }

    belief = NpcBelief(
        belief_id="belief_002",
        suspect_id="suspect_002",
        proposition="The inheritance dispute is important.",
        status=BeliefStatus.BELIEVES,
        confidence=0.8,
    )

    engine = EpistemicEngine(
        epistemic._authorization,
        knowledge,
        beliefs={"suspect_002": (belief,)},
    )

    assert engine.get_npc_beliefs("suspect_002") == (belief,)
    assert engine.get_npc_beliefs("suspect_001") == ()


def test_belief_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        NpcBelief(
            belief_id="belief_003",
            suspect_id="suspect_001",
            proposition="Test belief",
            confidence=1.5,
        )


def test_belief_rejects_invalid_status():
    with pytest.raises(ValueError):
        NpcBelief(
            belief_id="belief_004",
            suspect_id="suspect_001",
            proposition="Test belief",
            status="unknown_status",
        )


def test_engine_rejects_unknown_belief_fact(setup_engine):
    epistemic, _ = setup_engine

    knowledge = {
        suspect_id: epistemic.get_npc_knowledge(suspect_id)
        for suspect_id in (
            "suspect_001",
            "suspect_002",
            "suspect_003",
        )
    }

    belief = NpcBelief(
        belief_id="belief_005",
        suspect_id="suspect_001",
        proposition="An unknown fact is involved.",
        target_fact_id="fact_999",
    )

    with pytest.raises(ContractValidationError):
        EpistemicEngine(
            epistemic._authorization,
            knowledge,
            beliefs={"suspect_001": (belief,)},
        )


def test_dialogue_request_receives_only_revealable_facts(setup_engine):
    epistemic, _ = setup_engine
    state = make_stage_4_state()

    # Ask the Epistemic Engine what Kabir may reveal.
    knowledge = epistemic.get_authorized_knowledge(
        state,
        "suspect_002",
        presented_clue_ids=("clue_015",),
    )

    # Build a dialogue request using only revealable facts.
    request = DialogueRequest(
        request_id="request_test_001",
        case_id="case_001",
        suspect_id="suspect_002",
        player_message="Tell me about the financial transfer.",
        authorized_fact_ids=knowledge.revealable_fact_ids,
        presented_clue_ids=("clue_015",),
    )

    # Verify that the revealed fact can enter dialogue.
    assert request.has_authorized_fact("fact_028")

    # Verify that the concealed secret cannot enter dialogue.
    assert not request.has_authorized_fact("fact_017")

    # Verify the request contains only revealable facts.
    assert set(request.authorized_fact_ids) == set(
        knowledge.revealable_fact_ids
    )

    # Verify the evidence is correctly attached.
    assert request.has_presented_clue("clue_015")

    # Existing authorization service must accept this request.
    epistemic._authorization.validate_dialogue_request(
        state,
        request,
    )

def test_unlocked_filter_blocks_secret_fact_before_stage_4(
    setup_engine,
):
    epistemic, _ = setup_engine
    state = make_stage_3_state()

    knowledge = epistemic.get_authorized_knowledge(
        state,
        "suspect_002",
        presented_clue_ids=("clue_015",),
    )

    assert "fact_028" not in knowledge.available_fact_ids
    assert "fact_028" not in knowledge.revealable_fact_ids
