import os
import requests
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Resolve .env relative to this file so it works regardless of the
# working directory that uvicorn / the shell is launched from.
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

# Simple in-memory cache for API responses
_ai_cache = {}

def generate_ai_explanation(project_name, dependencies , issues):
    prompt = f"""
    You are an enterprise graph intelligence assistant.

    ONLY use the exact graph information provided.

    Do NOT:
    - invent architecture details
    - assume root causes
    - mention single points of failure
    - provide recommendations
    - add external business context

    Project:
    {project_name}

    Dependencies:
    {dependencies}

    Indirect Issues:
    {issues}

    Task:
    Explain briefly why the project risk is elevated using ONLY the dependencies and indirect issues listed above.

    Limit response to 40-60 words.
    """

    return _call_gemini(prompt)


def generate_chat_response(user_message, intent, context):
    """Generate a chat response based on user question, detected intent, and analysis context."""

    intent_instructions = {
        "risk_analysis": "Analyze the risk data provided. Highlight which projects/services are at high risk, their risk scores, and any active incidents. Be specific with numbers.",
        "impact_analysis": "Explain the blast radius — which systems are affected if the specified node fails, and why. Trace the dependency chain.",
        "root_cause": "Explain what is causing issues for the specified system. Trace through the dependency chain and identify which downstream incidents are contributing to the risk.",
        "skills_search": "List the matching team members, their skills, roles, and match percentage. Be helpful and specific.",
        "risk_mitigation": "Based on the system's dependencies, incidents, and team capabilities, suggest concrete risk mitigation steps. Be actionable and specific.",
        "summary": "Provide a concise executive summary of the overall system health, highlighting key risks, incident counts, and critical dependencies.",
        "dependency_analysis": "Explain the dependency chain for the specified system — what it depends on, and what depends on it.",
        "general": "Answer the user's question using the system context provided. Be helpful and specific."
    }

    instruction = intent_instructions.get(intent, intent_instructions["general"])

    prompt = f"""You are an Enterprise AI Management Assistant. You help engineering leaders understand project risks, team capabilities, and system dependencies.

RULES:
- ONLY use the data provided below. Do NOT invent information.
- Be concise but thorough (80-150 words).
- Use bullet points for lists.
- Include specific numbers (risk scores, counts) when available.
- If the data shows no issues, say so clearly.

USER QUESTION:
{user_message}

DETECTED INTENT: {intent}

ANALYSIS DATA:
{json.dumps(context, sort_keys=True, indent=2)}

TASK:
{instruction}
"""

    return _call_gemini(prompt)


def _call_gemini(prompt):
    """Shared Gemini call with error handling, retry logic, and caching."""
    cache_key = hash(prompt)
    if cache_key in _ai_cache:
        return _ai_cache[cache_key]

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_free_gemini_api_key_here":
        return (
            "⚠️ AI Analysis unavailable.\n\n"
            "Please configure your free **GEMINI_API_KEY** in the backend/.env file to enable instant AI reports.\n"
            "You can obtain a key for free in 30 seconds from Google AI Studio (https://aistudio.google.com/)."
        )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    max_retries = 3
    backoff = 2

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 429:
                print(f"[Gemini] 429 Rate Limit hit (attempt {attempt + 1}/{max_retries}).")
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                # All retries exhausted — return friendly message
                return (
                    "⏳ **AI Rate Limit Reached**\n\n"
                    "The Gemini API free-tier quota has been temporarily exhausted. "
                    "Please wait a minute and try again, or check your quota at "
                    "[Google AI Studio](https://aistudio.google.com/)."
                )
            
            if response.status_code == 200:
                data = response.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    parts = data["candidates"][0]["content"]["parts"]
                    if len(parts) > 0:
                        result = parts[0]["text"].strip()
                        _ai_cache[cache_key] = result
                        return result
                return "AI generated an empty response."
            else:
                return f"AI Analysis failed (Status {response.status_code})."
                
        except Exception as e:
            if attempt == max_retries - 1:
                return f"AI Analysis failed: {str(e)}"
    return "AI Analysis failed after multiple attempts."
