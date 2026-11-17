import json
import os
import pytest
from backend.shared.contracts.case import Case

# Path till case.json 
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CASE_JSON_PATH = os.path.join(BASE_DIR, "backend", "case_data", "case_001", "case.json")

def test_case_json_loads_correctly():
    # 1. JSON file load 
    with open(CASE_JSON_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    
    # 2. JSON dictionary to  Case dataclass (convert)
    # (Remember: JSON has  list , but  Case class wants tuple)
    valid_case = Case(
        case_id=data["case_id"],
        title=data["title"],
        description=data["description"],
        victim_id=data["victim_id"],
        suspect_ids=tuple(data["suspect_ids"]),
        fact_ids=tuple(data["fact_ids"]),
        clue_ids=tuple(data["clue_ids"]),
        timeline_event_ids=tuple(data["timeline_event_ids"]),
        schema_version=data["schema_version"]
    )
    
    # 3. Verify all loaded correctly
    assert valid_case.case_id == "case_001"
    assert len(valid_case.suspect_ids) == 3
    assert len(valid_case.fact_ids) == 44
    assert valid_case.has_fact("fact_042") is True