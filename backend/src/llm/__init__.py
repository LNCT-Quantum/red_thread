"""Red Thread LLM interrogation pipeline: inference, extraction, telemetry, and prompt synthesis."""

from .engine_runner import EngineError, LocalLLMEngine
from .extractor import ExtractionResult, FactExtractor
from .few_shot_examples import FEW_SHOT_EXAMPLES, render_few_shot_examples
from .profiler import LatencyProfiler, TurnMetricRecord
from .prompt_synthesizer import MAX_PLAYER_CHARS, build_prompt, synthesize_prompt
from .reply_checks import check_reply
from .service import InterrogationResponse, InterrogationService

__all__ = [
    "InterrogationService",
    "InterrogationResponse",
    "LocalLLMEngine",
    "EngineError",
    "FactExtractor",
    "ExtractionResult",
    "LatencyProfiler",
    "TurnMetricRecord",
    "build_prompt",
    "MAX_PLAYER_CHARS",
    "check_reply",
    "synthesize_prompt",
    "render_few_shot_examples",
    "FEW_SHOT_EXAMPLES",
]
