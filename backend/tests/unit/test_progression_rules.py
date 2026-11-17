# File: backend/tests/unit/test_progression_rules.py
import pytest
from src.progression.progression_rules import ProgressionRules, StageRule

def test_valid_progression_rules_with_description():
    # Create good rules with the  'description' field
    rules = ProgressionRules(
        case_id="case_001",
        stages=(
            StageRule(stage_id="stage_1", title="Start", description="The beginning"),
            StageRule(stage_id="stage_2", title="End", description="The end", required_clue_ids=("clue_001",))
        )
    )
    assert len(rules.stages) == 2
    assert rules.initial_stage.description == "The beginning"

def test_progression_rules_fails_if_reserved_prefix_used():
    # Test that a normal objective cannot use the system prefix 'stage:'
    with pytest.raises(ValueError, match="must not use a reserved prefix"):
        StageRule(
            stage_id="stage_1", 
            title="Start", 
            required_objective_ids=("stage:secret_stage",) # This is illegal
        )
    
    # Test that a normal objective cannot use the system prefix 'reaction:'
    with pytest.raises(ValueError, match="must not use a reserved prefix"):
        StageRule(
            stage_id="stage_1", 
            title="Start", 
            required_objective_ids=("reaction:evidence_001",) # This is also illegal
        )

def test_progression_rules_fails_if_initial_stage_has_requirements():
    # Test that the very first stage cannot have any requirements
    with pytest.raises(ValueError, match="the initial stage must not have requirements"):
        ProgressionRules(
            case_id="case_001",
            stages=(
                StageRule(stage_id="stage_1", title="Start", required_clue_ids=("clue_001",)),
            )
        )

def test_progression_rules_fails_on_duplicate_stage_ids():
    # Test that two stages cannot have the same ID
    with pytest.raises(ValueError, match="duplicate stage_id"):
        ProgressionRules(
            case_id="case_001",
            stages=(
                StageRule(stage_id="stage_1", title="Start"),
                StageRule(stage_id="stage_1", title="Duplicate")
            )
        )