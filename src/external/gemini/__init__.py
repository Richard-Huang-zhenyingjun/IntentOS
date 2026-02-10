"""
Gemini API integration for vision-based scene understanding.
Week 4: Gemini proposer integration.
"""
from src.external.gemini.types import GeminiRawResponse
from src.external.gemini.client import GeminiClientBase, RealGeminiClient
from src.external.gemini.client_fake import FakeGeminiClient
from src.external.gemini.prompts import build_scene_text, build_prompt, SCENE_ANALYSIS_PROMPT
from src.external.gemini.parser import parse_gemini_response, ParseResult
from src.external.gemini.cache import GeminiCache

__all__ = [
    'GeminiRawResponse', 
    'GeminiClientBase', 
    'RealGeminiClient', 
    'FakeGeminiClient',
    'build_scene_text',
    'build_prompt',
    'SCENE_ANALYSIS_PROMPT',
    'parse_gemini_response',
    'ParseResult',
    'GeminiCache',
]

