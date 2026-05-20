from dotenv import load_dotenv
load_dotenv(override=True)

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
import yaml
import re


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


def _parse_description_fallback(text):
    """Regex-based fallback for parsing Jira descriptions that aren't valid YAML."""
    result = {}

    # Extract single-value fields: project, service, owner_team
    for field in ["project", "service", "owner_team"]:
        match = re.search(rf'{field}\s*:\s*(.+)', text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            if value:
                result[field] = value

    # Extract depends_on list — look for lines after "depends_on:" that start with -, *, •, or just indented text
    depends_match = re.search(r'depends_on\s*:\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if depends_match:
        rest = depends_match.group(1)
        # Check if it's an inline value (e.g., "depends_on: payment-api")
        first_line = rest.split('\n')[0].strip()
        if first_line and not first_line.startswith('-') and not first_line.startswith('*'):
            # Single inline dependency
            result["depends_on"] = [first_line.strip('"').strip("'")]
        else:
            # Multi-line list items
            deps = re.findall(r'[\-\*•]\s*(.+)', rest)
            # Stop collecting when we hit the next field (owner_team, etc.)
            clean_deps = []
            for dep in deps:
                dep = dep.strip().strip('"').strip("'")
                if ':' in dep:
                    break  # hit the next key like "owner_team: ..."
                if dep:
                    clean_deps.append(dep)
            if clean_deps:
                result["depends_on"] = clean_deps

    print("FALLBACK PARSED:", result)
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
        print(f"[{ticket_id}] RAW DESCRIPTION:\n{raw_desc}")

        parsed_description: dict = {}
        try:
            parsed_description = yaml.safe_load(raw_desc) or {}
        except Exception:
            pass
        if not isinstance(parsed_description, dict) or not parsed_description:
            parsed_description = _parse_description_fallback(raw_desc)
            print(f"[{ticket_id}] Used fallback parser:", parsed_description)

        # 2. Determine service ID (Jira Label first, then description "service")
        service_id = incident["service"] or parsed_description.get("service")
        if not service_id:
            print(f"[{ticket_id}] SKIPPING ticket — no service label or description service provided")
            continue

        # Always create the service node — it represents real infrastructure
        node = ensure_node(service_id, "service")

        if is_done:
            # Done tickets: infrastructure nodes exist but carry 0 risk
            resolved_count += 1
            print(f"[{ticket_id}] RESOLVED — node created with no risk contribution")
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
            print(f"[{ticket_id}] ACTIVE — risk +{risk_score} on '{service_id}'")

        # ── Build graph structure from parsed description ────────
        project_id = parsed_description.get("project")
        if project_id:
            ensure_node(project_id, "project")
            add_edge(project_id, service_id, "depends_on")
            print(f"[{ticket_id}] EDGE: {project_id} -> {service_id} (depends_on)")

        owner_team = parsed_description.get("owner_team")
        if owner_team:
            ensure_node(owner_team, "team")
            add_edge(service_id, owner_team, "owned_by")
            print(f"[{ticket_id}] EDGE: {service_id} -> {owner_team} (owned_by)")

        dependencies = parsed_description.get("depends_on") or []
        if isinstance(dependencies, str):
            dependencies = [dependencies]
        for dep in dependencies:
            dep = dep.strip()
            if dep:
                ensure_node(dep, "service")
                add_edge(service_id, dep, "depends_on")
                print(f"[{ticket_id}] EDGE: {service_id} -> {dep} (depends_on)")

    # ── Replace graph entirely ───────────────────────────────────
    graph_data["nodes"] = list(new_nodes.values())
    graph_data["edges"] = new_edges
    save_graph_data()

    print(f"SYNC COMPLETE: {active_count} active, {resolved_count} resolved")
    print(f"Graph: {len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")

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
