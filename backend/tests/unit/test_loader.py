# File: backend/tests/unit/test_loader.py
import pytest
import json
from pathlib import Path
from shared.contracts.errors import ContractValidationError, ResourceNotFoundError
from src.case_engine.loader import load_case_data, CASE_FILES

@pytest.fixture
def valid_case_dir(tmp_path):
    # Create a temporary directory structure with valid JSON files
    case_dir = tmp_path / "case_001"
    case_dir.mkdir()
    
    # Minimal valid data to pass contracts (Updated timeline field to event_description)
    valid_data = {
        "case.json": {"case_id": "case_001", "title": "T", "description": "D", "victim_id": "v1", "suspect_ids": ["s1"], "fact_ids": ["f1"], "clue_ids": ["c1"], "timeline_event_ids": ["t1"]},
        "suspects.json": [{"suspect_id": "s1", "name": "N", "occupation": "O", "background": "B", "public_description": "P", "relationship_to_victim": "R", "speech_style": "S"}],
        "facts.json": [{"fact_id": "f1", "case_id": "case_001", "statement": "St", "category": "C", "importance": "I"}],
        "clues.json": [{"clue_id": "c1", "case_id": "case_001", "title": "T", "description": "D", "clue_type": "CT", "source": "S"}],
        "timeline.json": [{"timeline_event_id": "t1", "case_id": "case_001", "timestamp": "2023-01-01T00:00:00Z", "event_description": "D"}] # FIXED: 'description' changed to 'event_description'
    }
    
    for filename, data in valid_data.items():
        with open(case_dir / filename, "w", encoding="utf-8") as f:
            json.dump(data, f)
            
    return tmp_path

def test_load_valid_case_data(valid_case_dir):
    # Test that valid JSON files are loaded successfully
    case_data = load_case_data("case_001", data_root=valid_case_dir)
    assert case_data.case.case_id == "case_001"
    assert len(case_data.suspects) == 1
    assert len(case_data.facts) == 1

def test_load_case_invalid_id_format():
    # Test that an invalid case ID format is rejected
    with pytest.raises(ContractValidationError, match="Invalid case id"):
        load_case_data("case @ 001") # Invalid characters

def test_load_case_directory_not_found(tmp_path):
    # Test that missing directory throws ResourceNotFoundError
    with pytest.raises(ResourceNotFoundError, match="Case directory not found"):
        load_case_data("missing_case", data_root=tmp_path)

def test_load_case_missing_file(valid_case_dir):
    # Test that if a required file is missing, it throws an error
    # Delete one of the required files
    (valid_case_dir / "case_001" / "suspects.json").unlink()
    
    # Use raw string r"" to fix the SyntaxWarning
    with pytest.raises(ResourceNotFoundError, match=r"Required case file\(s\) missing"):
        load_case_data("case_001", data_root=valid_case_dir)

def test_load_case_malformed_json(valid_case_dir):
    # Test that a file with invalid JSON syntax throws an error
    # Overwrite facts.json with malformed JSON
    with open(valid_case_dir / "case_001" / "facts.json", "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")
        
    with pytest.raises(ContractValidationError, match="could not be parsed as JSON"):
        load_case_data("case_001", data_root=valid_case_dir)