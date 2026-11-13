import json
import os
import pytest
from typing import List, Dict

# ---------------------------------------------------------
# 1. MOCK CONTEXT BUILDER (because owner 3 work is left(i.e dialogue generation))
# ---------------------------------------------------------
class MockContextBuilder:
    def __init__(self, npc_knowledge_data: List[Dict]):
        self.knowledge_data = npc_knowledge_data

    def build_prompt_facts(self, suspect_id: str) -> List[str]:
        """
        Yeh function simulate karta hai ki Context Builder kaise facts filter karega.
        Sirf 'known_fact_ids' ko prompt mein bhejega.
        """
        for suspect in self.knowledge_data:
            if suspect["suspect_id"] == suspect_id:
                # Sirf known facts return karo
                return suspect.get("known_fact_ids", [])
        return []

# ---------------------------------------------------------
# 2. FIXTURES (Data Loader)
# ---------------------------------------------------------
@pytest.fixture
def npc_knowledge_data():
    # Path setup 
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    filepath = os.path.join(base_dir, "backend", "case_data", "case_001", "npc_knowledge.json")
    
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture
def context_builder(npc_knowledge_data):
    return MockContextBuilder(npc_knowledge_data)

# ---------------------------------------------------------
# 3. TESTS (Epistemic Masking)
# ---------------------------------------------------------

def test_context_builder_only_includes_known_facts(context_builder):
    # Suspect 1 (Anaya) ke liye prompt facts get 
    prompt_facts = context_builder.build_prompt_facts("suspect_001")
    
    # Verify: anaya knows fact_001 , so should be there in prompt
    assert "fact_001" in prompt_facts
    assert "fact_010" in prompt_facts
    
    # Verify: fact_019 anaya's secret , should not be there in prompt
    assert "fact_019" not in prompt_facts
    
    # Verify: anaya does not know fact_044 , should not be there in prompt
    assert "fact_044" not in prompt_facts

def test_context_builder_masks_unknown_facts(context_builder):
    # Suspect 2 (Kabir) check
    prompt_facts = context_builder.build_prompt_facts("suspect_002")
    
    # Verify: fact_017 is his secret,so should not be there in prompts
    assert "fact_017" not in prompt_facts
    
    # Verify: fact_001 he knows, so should be there in prompt
    assert "fact_001" in prompt_facts

def test_context_builder_returns_empty_for_unknown_suspect(context_builder):
    # if suspect id does not exist --> empty prompt
    prompt_facts = context_builder.build_prompt_facts("suspect_999")
    assert prompt_facts == []