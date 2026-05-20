import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"

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

    return _call_ollama(prompt)


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
{json.dumps(context, indent=2)}

TASK:
{instruction}
"""

    return _call_ollama(prompt)


def _call_ollama(prompt):
    """Shared Ollama call with error handling."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": "qwen2.5:1.5b",
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        data = response.json()
        return data.get("response", "AI could not generate a response.")
    except requests.exceptions.ConnectionError:
        print("Ollama is not running or not reachable.")
        return "AI Analysis unavailable — Ollama is not running."
    except requests.exceptions.Timeout:
        print("Ollama request timed out.")
        return "AI Analysis timed out. Try again."
    except Exception as e:
        print(f"AI engine error: {e}")
        return f"AI Analysis failed: {str(e)}"

