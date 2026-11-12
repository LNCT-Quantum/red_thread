# File: backend/tests/contract/test_progression_contract.py
import pytest
from shared.contracts.progression import ProgressionStage, Progression

def test_valid_progression_stage_creation():
    # Test creating a valid stage with all fields
    stage = ProgressionStage(
        stage_id="stage_1",
        title="The Beginning",
        description="Start of the game",
        required_clue_ids=("clue_001",),
        unlocks_fact_ids=("fact_001",)
    )
    assert stage.stage_id == "stage_1"
    assert "clue_001" in stage.required_clue_ids

def test_stage_fails_on_empty_title():
    # Test that an empty title throws an error
    with pytest.raises(ValueError, match="title must be a non-empty string"):
        ProgressionStage(
            stage_id="stage_1",
            title="   ", # Empty space
            description="Some description"
        )

def test_stage_fails_on_duplicate_clue_ids():
    # Test that duplicate clues are rejected
    with pytest.raises(ValueError, match="Duplicate ID 'clue_001'"):
        ProgressionStage(
            stage_id="stage_1",
            title="Title",
            description="Desc",
            required_clue_ids=("clue_001", "clue_001") # Duplicate
        )

def test_valid_progression_creation():
    # Test creating a full progression with multiple stages
    stage1 = ProgressionStage(stage_id="s1", title="Start", description="Desc")
    stage2 = ProgressionStage(stage_id="s2", title="End", description="Desc")
    
    prog = Progression(stages=(stage1, stage2))
    
    # Test helper methods
    assert prog.first_stage.stage_id == "s1"
    assert prog.final_stage.stage_id == "s2"
    assert prog.get_stage("s1") == stage1
    assert prog.get_next_stage("s1") == stage2
    assert prog.get_next_stage("s2") is None

def test_progression_fails_on_duplicate_stage_ids():
    # Test that two stages cannot have the same ID
    stage1 = ProgressionStage(stage_id="s1", title="Start", description="Desc")
    stage2 = ProgressionStage(stage_id="s1", title="End", description="Desc") # Duplicate ID
    
    with pytest.raises(ValueError, match="Duplicate stage_id 's1'"):
        Progression(stages=(stage1, stage2))

def test_progression_from_json():
    # Test parsing a valid JSON string
    json_data = '''
    {
        "stages": [
            {"stage_id": "s1", "title": "Start", "description": "Beginning"},
            {"stage_id": "s2", "title": "End", "description": "Ending"}
        ]
    }
    '''
    prog = Progression.from_json(json_data)
    assert len(prog.stages) == 2
    assert prog.stages[1].title == "End"

def test_progression_from_invalid_json():
    # Test that a malformed JSON string throws an error
    with pytest.raises(ValueError, match="Invalid progression JSON"):
        Progression.from_json("{ not valid json }")