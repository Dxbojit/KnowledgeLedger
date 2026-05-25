from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

import logging
import yaml
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from graph_data import graph_data, save_graph_data
from risk_engine import propagate_risk
from ai_engine import generate_ai_explanation
from jira_service import fetch_jira_issues
from chat_router import process_chat_message
from team_data import team_data, save_team_data
from analysis_functions import get_executive_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ─── Request Models ────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class TeamMemberRequest(BaseModel):
    id: str
    name: str
    team: str
    skills: List[str]
    role: Optional[str] = "Developer"

app = FastAPI()
# No in-memory ticket state — graph is rebuilt fresh from Jira on every sync

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


def find_indirect_issues(start_node_id,nodes,edges):
    visited = set()
    found_issues=[]

    def traverse(node_id):

        if node_id in visited:
            return
        visited.add(node_id)
        outgoing_Edges = [
            edge for edge in edges
            if edge["source"] == node_id
        ]

        for edge in outgoing_Edges:

            target_id = edge["target"]

            target_node = next (
                (n for n in nodes if n["id"] == target_id),
                None
            )
            if not target_node:
                continue
            if "latest_incident" in target_node:
                found_issues.append(
                    target_node["latest_incident"]
                )
            
            traverse(target_id)
    traverse(start_node_id)

    return list(set(found_issues))

@app.get("/")
def home():
    return{
        "message" : "Knowledge Ledger Backend is Running"
    }

@app.get("/graph")
def get_graph():
    updated_nodes= propagate_risk()

    return{
        "nodes":updated_nodes,
        "edges":graph_data["edges"]
    }

@app.get("/ai-analysis/{node_id}")
def ai_analysis(node_id: str):
    nodes =graph_data["nodes"]
    edges= graph_data["edges"]

    node = next((n for n in nodes if n["id"] == node_id),None)

    if not node:
        return {"error": "Node not found"}

    dependencies=[]
    issues=find_indirect_issues(
        node_id,
        nodes,
        edges
    )

    for edge in edges:
        if edge["source"] == node_id:
            target = next(
                (n for n in nodes if n["id"] == edge["target"]),
                None
            )
            if target:
                dependencies.append(target["label"])
    explanation = generate_ai_explanation(
        node["label"],
        dependencies,
        issues
    )

    return{
        "analysis":explanation
    }


# ─── Slug Extractor ───────────────────────────────────────────────────────────
# All node IDs use kebab-case: project-atlas, auth-service, infra-team.
# A slug is one-or-more lowercase alphanumeric words joined by hyphens.
_SLUG_RE = re.compile(r'\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\b', re.IGNORECASE)

def _extract_slug(raw) -> str:
    """Return the first kebab-case identifier found in `raw`.

    Jira descriptions often contain trailing prose on the same line as the
    field value, e.g.  'project: project-atlas Some Description Here'.
    The user's rule: all node IDs are in x-name format (words connected by
    hyphens). So we scan the raw value for the first hyphenated slug token
    and return it, discarding everything else.

    If the value has no hyphen (single-word ids like 'atlas'), we fall back
    to returning the first non-empty whitespace-separated token lowercased.
    """
    if not raw:
        return ""
    raw = str(raw).strip().strip('"').strip("'")

    # Prefer first token that contains at least one hyphen
    for token in raw.split():
        token = token.strip('.,;:"\'')
        if re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)+$', token, re.IGNORECASE):
            return token.lower()

    # Fallback: first non-empty word, lowercased
    tokens = raw.split()
    return tokens[0].lower().strip('.,;:"\'') if tokens else ""


def _parse_description_fallback(text):
    """Regex-based fallback for parsing Jira descriptions that aren't valid YAML.
    All extracted values are normalised through _extract_slug() so that trailing
    prose (e.g. 'project-atlas description of project') is stripped cleanly.
    """
    result = {}

    # Extract single-value fields: project, service, owner_team
    for field in ["project", "service", "owner_team"]:
        match = re.search(rf'{field}\s*[:\s]\s*(.+)', text, re.IGNORECASE)
        if match:
            slug = _extract_slug(match.group(1))
            if slug:
                result[field] = slug

    # Extract depends_on list — lines after "depends_on:" that start with -, *, •
    depends_match = re.search(r'depends_on\s*[:\s]\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if depends_match:
        rest = depends_match.group(1)
        first_line = rest.split('\n')[0].strip()
        if first_line and not first_line.startswith('-') and not first_line.startswith('*'):
            # Inline single dependency: 'depends_on: payment-api'
            slug = _extract_slug(first_line)
            if slug:
                result["depends_on"] = [slug]
        else:
            # Multi-line list items
            deps = re.findall(r'[\-\*•]\s*(.+)', rest)
            clean_deps = []
            for dep in deps:
                dep = dep.strip()
                if ':' in dep and not dep.startswith('-'):
                    break  # hit the next key like "owner_team: ..."
                slug = _extract_slug(dep)
                if slug:
                    clean_deps.append(slug)
            if clean_deps:
                result["depends_on"] = clean_deps

    logger.debug("FALLBACK PARSED: %s", result)
    return result

@app.post("/sync-incidents")
def sync_incidents():
    """Rebuild the graph entirely from live Jira data on every call.
    No in-memory state. No JSON accumulation. The graph is always a
    pure reflection of what Jira currently contains.
    """
    jira_issues = fetch_jira_issues()

    severity_map = {"HIGH": 50, "MEDIUM": 30, "LOW": 15}

    # ── Fresh graph accumulators ─────────────────────────────────
    new_nodes: dict = {}   # node_id -> node dict
    seen_edges: set = set()  # (source, target, label) for dedup
    new_edges: list = []

    def ensure_node(node_id: str, node_type: str) -> dict:
        if node_id not in new_nodes:
            new_nodes[node_id] = {
                "id": node_id,
                "label": node_id.replace("-", " ").title(),
                "type": node_type,
                "risk_score": 0,
                "incidents": [],
                "latest_incident": None,
            }
        return new_nodes[node_id]

    def add_edge(source: str, target: str, label: str):
        key = (source, target, label)
        if key not in seen_edges:
            seen_edges.add(key)
            new_edges.append({"source": source, "target": target, "label": label})

    active_count = 0
    resolved_count = 0

    for incident in jira_issues:
        ticket_id = incident["ticket_id"]
        is_done = incident.get("is_done", False)

        # 1. Parse description first
        raw_desc = incident["description"].strip()
        logger.debug("[%s] RAW DESCRIPTION:\n%s", ticket_id, raw_desc)

        parsed_description: dict = {}
        try:
            parsed_description = yaml.safe_load(raw_desc) or {}
        except Exception:
            pass
        if not isinstance(parsed_description, dict) or not parsed_description:
            parsed_description = _parse_description_fallback(raw_desc)
            logger.debug("[%s] Used fallback parser: %s", ticket_id, parsed_description)

        # 2. Determine service ID (Jira Label first, then description "service")
        raw_service = incident["service"] or parsed_description.get("service") or ""
        service_id = _extract_slug(raw_service)
        if not service_id:
            logger.warning("[%s] SKIPPING ticket — no service label or description service provided", ticket_id)
            continue

        # Always create the service node — it represents real infrastructure
        node = ensure_node(service_id, "service")

        if is_done:
            # Done tickets: infrastructure nodes exist but carry 0 risk
            resolved_count += 1
            logger.info("[%s] RESOLVED — node created with no risk contribution", ticket_id)
        else:
            # Active tickets: add risk + incident
            active_count += 1
            risk_score = severity_map.get(incident["severity"], 10)
            node["risk_score"] += risk_score

            already_recorded = any(
                i["title"] == incident["title"] and i["severity"] == incident["severity"]
                for i in node["incidents"]
            )
            if not already_recorded:
                node["incidents"].append({
                    "title": incident["title"],
                    "severity": incident["severity"],
                })
            node["latest_incident"] = node["incidents"][-1]["title"] if node["incidents"] else None
            logger.info("[%s] ACTIVE — risk +%d on '%s'", ticket_id, risk_score, service_id)

        # ── Build graph structure from parsed description ────────
        project_id = _extract_slug(parsed_description.get("project") or "")
        if project_id:
            ensure_node(project_id, "project")
            add_edge(project_id, service_id, "depends_on")
            logger.debug("[%s] EDGE: %s -> %s (depends_on)", ticket_id, project_id, service_id)

        owner_team = _extract_slug(parsed_description.get("owner_team") or "")
        if owner_team:
            ensure_node(owner_team, "team")
            add_edge(service_id, owner_team, "owned_by")
            logger.debug("[%s] EDGE: %s -> %s (owned_by)", ticket_id, service_id, owner_team)

        dependencies = parsed_description.get("depends_on") or []
        if isinstance(dependencies, str):
            dependencies = [dependencies]
        for dep in dependencies:
            dep_slug = _extract_slug(dep)
            if dep_slug:
                ensure_node(dep_slug, "service")
                add_edge(service_id, dep_slug, "depends_on")
                logger.debug("[%s] EDGE: %s -> %s (depends_on)", ticket_id, service_id, dep_slug)

    # ── Replace graph entirely ───────────────────────────────────
    graph_data["nodes"] = list(new_nodes.values())
    graph_data["edges"] = new_edges
    save_graph_data()

    logger.info("SYNC COMPLETE: %d active, %d resolved", active_count, resolved_count)
    logger.info("Graph: %d nodes, %d edges", len(graph_data["nodes"]), len(graph_data["edges"]))

    return {
        "message": "Jira incidents synced successfully",
        "active_incidents": active_count,
        "resolved_incidents": resolved_count,
    }


# ─── Chat Endpoint ─────────────────────────────────────────────

@app.post("/chat")
def chat(request: ChatRequest):
    result = process_chat_message(request.message, request.session_id)
    return result


# ─── Team Endpoints ────────────────────────────────────────────

@app.get("/teams")
def get_teams():
    return team_data


@app.post("/teams/member")
def add_team_member(member: TeamMemberRequest):
    # Check if member already exists
    existing = next(
        (m for m in team_data["members"] if m["id"] == member.id),
        None
    )
    if existing:
        # Update existing member
        existing["name"] = member.name
        existing["team"] = member.team
        existing["skills"] = member.skills
        existing["role"] = member.role
    else:
        team_data["members"].append(member.model_dump())

    save_team_data()
    return {"message": f"Member {member.name} saved successfully"}


# ─── Summary Endpoint ─────────────────────────────────────────

@app.get("/summary")
def get_summary():
    return get_executive_summary()


# ─── Skills Search Endpoint ────────────────────────────────────

@app.get("/teams/skills/{skill}")
def get_members_by_skill(skill: str):
    """Fetch team members who have a specific skill."""
    matching_members = [
        member for member in team_data["members"]
        if any(s.lower() == skill.lower() for s in member.get("skills", []))
    ]
    
    return {
        "skill": skill,
        "count": len(matching_members),
        "members": matching_members
    }
