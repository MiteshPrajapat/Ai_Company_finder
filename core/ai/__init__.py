"""
AI Module for OpenRouter LLM integration, resume parsing, job match calculation, and personalized email generation.
"""

from core.ai.resume_extractor import ResumeExtractor
from core.ai.openrouter_client import OpenRouterClient
from core.ai.prompt_builders import PromptBuilder

__all__ = ["ResumeExtractor", "OpenRouterClient", "PromptBuilder"]
