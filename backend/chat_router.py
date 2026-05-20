"""
Chat router — detects user intent via keyword matching,
runs the appropriate analysis function, and sends context to Ollama.
"""

import json
import re
from graph_data import graph_data
from analysis_functions import (
    get_high_risk_projects,
    get_impact_analysis,
    get_root_cause,
    find_skilled_members,
    get_risk_mitigation_context,
    get_executive_summary,
)
from ai_engine import generate_chat_response


def extract_node_from_message(message):
    """Try to match a node ID or label from the user's message."""
    nodes = graph_data["nodes"]
    msg_lower = message.lower()

    # Try exact ID match first
    for node in nodes:
        if node["id"].lower() in msg_lower:
            return node["id"]

    # Try label match
    for node in nodes:
        if node["label"].lower() in msg_lower:
            return node["id"]

    # Try partial match (e.g., "payment" matches "payment-api")
    for node in nodes:
        label_words = node["label"].lower().split()
        for word in label_words:
            if len(word) > 3 and word in msg_lower:
                return node["id"]

    return None


def extract_skills_from_message(message):
    """Extract skill names from a user message."""
    # Common tech skills to look for
    known_skills = [
        "python", "java", "spring boot", "springboot", "react", "next.js",
        "nextjs", "node.js", "nodejs", "typescript", "javascript", "docker",
        "kubernetes", "aws", "azure", "gcp", "mongodb", "postgresql",
        "postgres", "mysql", "redis", "kafka", "fastapi", "flask",
        "django", "machine learning", "ml", "ai", "devops", "ci/cd",
        "terraform", "ansible", "go", "golang", "rust", "c++", "c#",
        ".net", "angular", "vue", "svelte", "graphql", "rest api",
    ]

    msg_lower = message.lower()
    found = []

    for skill in known_skills:
        if skill in msg_lower:
            # Normalize some variations
            normalized = skill
            if skill == "springboot":
                normalized = "spring boot"
            elif skill in ("nodejs", "node.js"):
                normalized = "Node.js"
            elif skill in ("nextjs", "next.js"):
                normalized = "Next.js"
            elif skill in ("ml",):
                normalized = "Machine Learning"
            found.append(normalized)

    # If no known skills found, try to extract quoted or capitalized words
    if not found:
        # Look for quoted terms
        quoted = re.findall(r'["\']([^"\']+)["\']', message)
        if quoted:
            found = quoted
        else:
            # Look for capitalized words that might be tech names
            caps = re.findall(r'\b([A-Z][a-zA-Z+#.]*)\b', message)
            found = [w for w in caps if len(w) > 1 and w not in ("Which", "Who", "What", "How", "Can", "Does", "The", "And", "For")]

    return found if found else ["general"]


def route_question(message):
    """
    Route a user question to the appropriate analysis function.
    Returns (intent, context_data) tuple.
    """
    msg = message.lower()

    # ─── Risk Analysis ─────────────────────────────────────────
    if any(w in msg for w in ["high risk", "risky", "at risk", "highest risk", "most risk", "risk level"]):
        context = get_high_risk_projects()
        return "risk_analysis", context

    # ─── Impact Analysis ───────────────────────────────────────
    if any(w in msg for w in ["fails", "goes down", "affected", "impact", "what happens if", "breaks", "crashes"]):
        node_id = extract_node_from_message(message)
        if node_id:
            context = get_impact_analysis(node_id)
            return "impact_analysis", context
        else:
            return "need_node", {
                "message": "I need to know which system you're asking about.",
                "available_nodes": [
                    {"id": n["id"], "label": n["label"], "type": n["type"]}
                    for n in graph_data["nodes"]
                ]
            }

    # ─── Root Cause Analysis ───────────────────────────────────
    if any(w in msg for w in ["causing", "root cause", "why is", "what is wrong", "failing", "problem with"]):
        node_id = extract_node_from_message(message)
        if node_id:
            context = get_root_cause(node_id)
            return "root_cause", context
        else:
            return "need_node", {
                "message": "Which system are you asking about?",
                "available_nodes": [
                    {"id": n["id"], "label": n["label"], "type": n["type"]}
                    for n in graph_data["nodes"]
                ]
            }

    # ─── Skills Search ─────────────────────────────────────────
    if any(w in msg for w in ["knows", "skills", "who can", "who has", "resources", "developers", "engineer", "team member"]):
        skills = extract_skills_from_message(message)
        context = find_skilled_members(skills)
        return "skills_search", context

    # ─── Mitigation ────────────────────────────────────────────
    if any(w in msg for w in ["mitigat", "fix", "resolve", "reduce risk", "prevent", "solution"]):
        node_id = extract_node_from_message(message)
        if node_id:
            context = get_risk_mitigation_context(node_id)
            return "risk_mitigation", context
        else:
            # General mitigation — use summary
            context = get_executive_summary()
            return "risk_mitigation", context

    # ─── Summary / Overview ────────────────────────────────────
    if any(w in msg for w in ["summary", "overview", "status", "report", "dashboard", "overall", "how are", "health"]):
        context = get_executive_summary()
        return "summary", context

    # ─── Dependencies ──────────────────────────────────────────
    if any(w in msg for w in ["depends", "dependency", "dependencies", "connected", "linked"]):
        node_id = extract_node_from_message(message)
        if node_id:
            context = get_root_cause(node_id)  # reuse — it shows dependency chain
            return "dependency_analysis", context
        else:
            context = get_executive_summary()
            return "dependency_analysis", context

    # ─── Fallback: General question with full context ──────────
    context = get_executive_summary()
    return "general", context


def process_chat_message(message):
    """
    Main entry point for chat. Routes the question, builds context,
    and sends to Ollama for a natural language response.
    """
    intent, context = route_question(message)

    # If we need more info from user, return immediately
    if intent == "need_node":
        available = ", ".join([n["label"] for n in context["available_nodes"]])
        return {
            "reply": f"{context['message']} Available systems: {available}",
            "intent": intent,
            "data": context,
            "needs_clarification": True
        }

    # Build the AI response
    ai_reply = generate_chat_response(message, intent, context)

    return {
        "reply": ai_reply,
        "intent": intent,
        "data": context,
        "needs_clarification": False
    }
