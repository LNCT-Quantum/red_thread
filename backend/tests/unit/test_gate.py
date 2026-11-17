# File: backend/tests/unit/test_gate.py
import pytest
from unittest.mock import MagicMock
from src.progression.gate import ProgressionGate
from src.progression.progression_manager import ProgressionManager
from src.progression.authorization import AuthorizationService
from src.progression.progression_rules import ProgressionRules, StageRule
from src.progression.knowledge import NpcKnowledge

def test_progression_gate_initialization():
    # Create fake objects for dependencies
    fake_manager = MagicMock(spec=ProgressionManager)
    fake_auth = MagicMock(spec=AuthorizationService)

    # Initialize the gate
    gate = ProgressionGate(manager=fake_manager, authorization=fake_auth)

    # Check if it saved them correctly
    assert gate.manager == fake_manager
    assert gate.authorization == fake_auth

def test_progression_gate_from_engine_with_knowledge():
    # Create fake engine, rules, and knowledge to avoid loading real files
    fake_engine = MagicMock()
    fake_engine.case_id = "case_001"
    
    fake_rules = ProgressionRules(
        case_id="case_001",
        stages=(StageRule(stage_id="stage_1", title="Start"),)
    )
    
    fake_knowledge = {
        "suspect_001": NpcKnowledge(
            suspect_id="suspect_001",
            known_fact_ids=(),
            unknown_fact_ids=(),
            secret_fact_ids=()
        )
    }

    # Call from_engine and pass the fake data explicitly
    gate = ProgressionGate.from_engine(
        engine=fake_engine, 
        rules=fake_rules, 
        knowledge=fake_knowledge
    )
    
    # Verify it returns the correct type
    assert isinstance(gate, ProgressionGate)
    assert gate.manager is not None
    assert gate.authorization is not None