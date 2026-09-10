"""
Prompt engineering and response parsing for Job Analysis, Resume Matching, and Personalized Email Generation.
"""

import json
import re
from typing import Dict, Any, Optional, List
from database.models import AIAnalysisResult
from utils.logger import get_logger

logger = get_logger("prompt_builders")


class PromptBuilder:
    """Constructs tailored system and user prompts for job analysis and email drafting."""

    SYSTEM_PROMPT = """You are an elite AI Career Advisor and Executive Talent Matcher.
Your role is to deeply analyze job descriptions, compare them with a candidate's real resume, calculate realistic match scores, and craft highly persuasive, authentic, and professional job application / cold outreach emails for hiring managers and recruiters.

Rules:
1. Never fabricate skills or experience that are not present in the candidate's resume.
2. Ensure the tone is authentic, confident, and polite. Avoid robotic buzzwords or generic fluff.
3. Always return valid JSON matching the requested schema.
"""

    @staticmethod
    def build_analysis_and_email_prompt(
        job_title: str,
        company_name: str,
        job_description: str,
        resume_text: str,
        candidate_info: Dict[str, str],
        tone: str = "Professional & Concise"
    ) -> str:
        """
        Builds a comprehensive prompt for job analysis, skill extraction, match scoring, and personalized email generation.
        """
        candidate_name = candidate_info.get("name") or "[Your Name]"
        candidate_email = candidate_info.get("email") or "[Your Email]"
        candidate_phone = candidate_info.get("phone") or "[Your Phone]"
        candidate_linkedin = candidate_info.get("linkedin") or "[LinkedIn Profile]"
        candidate_portfolio = candidate_info.get("portfolio") or ""

        prompt = f"""
Analyze the following Job Description against the Candidate's Resume.

---
### TARGET JOB DETAILS
- **Job Title**: {job_title}
- **Company Name**: {company_name}
- **Job Description & Requirements**:
{job_description or "Not specified"}

---
### CANDIDATE RESUME
{resume_text or "No resume text provided."}

---
### CANDIDATE CONTACT INFO
- **Name**: {candidate_name}
- **Email**: {candidate_email}
- **Phone**: {candidate_phone}
- **LinkedIn**: {candidate_linkedin}
{f'- **Portfolio/GitHub**: {candidate_portfolio}' if candidate_portfolio else ''}

---
### DESIRED EMAIL TONE: {tone}

---
### REQUIRED OUTPUT FORMAT (JSON ONLY)
Respond ONLY with a valid JSON object with the following structure:
{{
  "match_score": 88,
  "required_skills": ["Java", "Spring Boot", "SQL", "REST API"],
  "preferred_skills": ["Docker", "AWS", "Kafka"],
  "matched_skills": ["Java", "Spring Boot", "SQL", "REST API", "Docker"],
  "missing_skills": ["AWS", "Kafka"],
  "experience_level": "1-3 years",
  "summary": "Brief 1-2 sentence assessment of fit.",
  "generated_subject": "Application for {job_title} – {candidate_name}",
  "generated_body": "Dear Hiring Manager,\\n\\n..."
}}

EMAIL WRITING GUIDELINES:
1. Subject: Clear, professional, including the job title and candidate's name.
2. Opening: State exact interest in the {job_title} position at {company_name}.
3. Body: Highlight 2-3 specific technical skills / project accomplishments from the resume that directly match the job requirements.
4. Call to Action: Politely mention the attached resume and ask for an introductory interview / conversation.
5. Sign-off: Professional sign-off including {candidate_name}, Phone, Email, and LinkedIn.
6. Do NOT include markdown code blocks in the generated_body; use standard newline characters.
"""
        return prompt

    @staticmethod
    def build_regenerate_email_prompt(
        job_title: str,
        company_name: str,
        job_description: str,
        resume_text: str,
        candidate_info: Dict[str, str],
        custom_instructions: str,
        tone: str = "Professional & Concise"
    ) -> str:
        """
        Builds prompt to re-generate an email based on user custom instructions.
        """
        candidate_name = candidate_info.get("name") or "[Your Name]"
        candidate_email = candidate_info.get("email") or "[Your Email]"
        candidate_phone = candidate_info.get("phone") or "[Your Phone]"
        candidate_linkedin = candidate_info.get("linkedin") or "[LinkedIn Profile]"

        prompt = f"""
Re-generate the job application / HR outreach email with the following modifications:

- **Target Job**: {job_title} at {company_name}
- **Desired Tone**: {tone}
- **Custom User Instructions**: {custom_instructions}

---
### CANDIDATE RESUME SUMMARY
{resume_text[:2000] if resume_text else "General candidate background."}

---
### CANDIDATE CONTACT INFO
- **Name**: {candidate_name}
- **Email**: {candidate_email}
- **Phone**: {candidate_phone}
- **LinkedIn**: {candidate_linkedin}

---
### REQUIRED OUTPUT FORMAT (JSON ONLY)
{{
  "generated_subject": "Application for {job_title} – {candidate_name}",
  "generated_body": "Dear Hiring Manager,\\n\\n..."
}}
"""
        return prompt

    @staticmethod
    def parse_ai_response(response_text: str) -> AIAnalysisResult:
        """
        Parses the JSON response from the LLM into a structured AIAnalysisResult object.
        """
        clean_json = response_text.strip()
        # Strip markdown fences if present
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
            clean_json = re.sub(r"\n?```$", "", clean_json)

        # Look for the first { and last }
        match = re.search(r"\{.*\}", clean_json, re.DOTALL)
        if match:
            clean_json = match.group(0)

        try:
            data = json.loads(clean_json)
            return AIAnalysisResult(
                match_score=int(data.get("match_score", 70)),
                required_skills=list(data.get("required_skills", [])),
                preferred_skills=list(data.get("preferred_skills", [])),
                matched_skills=list(data.get("matched_skills", [])),
                missing_skills=list(data.get("missing_skills", [])),
                experience_level=str(data.get("experience_level", "")),
                summary=str(data.get("summary", "")),
                generated_subject=str(data.get("generated_subject", "")),
                generated_body=str(data.get("generated_body", "")),
                raw_response=response_text
            )
        except Exception as e:
            logger.warning(f"Failed to parse AI JSON response: {e}. Falling back to plain text extraction.")
            # Fallback parsing
            return AIAnalysisResult(
                match_score=75,
                summary="AI analysis completed.",
                generated_subject="Application for Job Position",
                generated_body=response_text,
                raw_response=response_text
            )
