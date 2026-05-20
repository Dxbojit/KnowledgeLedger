from dotenv import load_dotenv
load_dotenv()

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

class TeamMemberRequest(BaseModel):
    id: str
    name: str
    team: str
    skills: List[str]
    role: Optional[str] = "Developer"

app = FastAPI()
synced_ticket_ids = set()       # tickets we've processed as active
resolved_ticket_ids = set()     # tickets we've already resolved
ticket_risk_map = {}            # ticket_id -> {service_id, risk_score, title}

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

def _ensure_node(node_id, node_type, existing_ids):
    """Create a node if it doesn't already exist in graph_data."""
    if node_id not in existing_ids:
        graph_data["nodes"].append({
            "id": node_id,
            "label": node_id.replace("-", " ").title(),
            "type": node_type,
            "risk_score": 0
        })
        existing_ids.add(node_id)


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
    jira_issues = fetch_jira_issues()

    severity_map = {
        "HIGH": 50,
        "MEDIUM": 30,
        "LOW": 15
    }

    existing_ids = {node["id"] for node in graph_data["nodes"]}

    # ── Detect DELETED tickets (were synced before, now gone from Jira) ─────
    current_jira_ids = {i["ticket_id"] for i in jira_issues}
    deleted_ticket_ids = (
        synced_ticket_ids - current_jira_ids - resolved_ticket_ids
    )

    for deleted_id in deleted_ticket_ids:
        stored = ticket_risk_map.get(deleted_id)
        if stored:
            # Reverse risk + remove incident from service node
            node = next((n for n in graph_data["nodes"] if n["id"] == stored["service_id"]), None)
            if node:
                node["risk_score"] = max(0, node["risk_score"] - stored["risk_score"])
                node["incidents"] = [
                    i for i in node.get("incidents", [])
                    if i["title"] != stored["title"]
                ]
                remaining = node.get("incidents", [])
                node["latest_incident"] = remaining[-1]["title"] if remaining else None

            # Remove nodes this ticket created (only if no other active ticket references them)
            other_service_ids = {
                v["service_id"] for k, v in ticket_risk_map.items()
                if k != deleted_id and k in synced_ticket_ids and k not in resolved_ticket_ids
            }
            for node_id in stored.get("created_node_ids", []):
                if node_id not in other_service_ids:
                    graph_data["nodes"] = [n for n in graph_data["nodes"] if n["id"] != node_id]
                    graph_data["edges"] = [
                        e for e in graph_data["edges"]
                        if e["source"] != node_id and e["target"] != node_id
                    ]
                    existing_ids.discard(node_id)
                    print(f"DELETED node: {node_id} (ticket {deleted_id} removed)")

            # Remove edges this ticket explicitly created
            for edge in stored.get("created_edges", []):
                graph_data["edges"] = [
                    e for e in graph_data["edges"]
                    if not (e["source"] == edge["source"] and e["target"] == edge["target"] and e["label"] == edge["label"])
                ]
                print(f"DELETED edge: {edge['source']} -> {edge['target']} (ticket {deleted_id} removed)")

        synced_ticket_ids.discard(deleted_id)
        ticket_risk_map.pop(deleted_id, None)
        print(f"DELETED ticket {deleted_id} — reverted its graph contributions")


    for incident in jira_issues:
        ticket_id = incident["ticket_id"]
        is_done = incident.get("is_done", False)

        # ── Ticket RESOLVED: reverse its risk contribution ──────
        if is_done and ticket_id in synced_ticket_ids and ticket_id not in resolved_ticket_ids:
            resolved_ticket_ids.add(ticket_id)
            stored = ticket_risk_map.get(ticket_id)
            if stored:
                node = next((n for n in graph_data["nodes"] if n["id"] == stored["service_id"]), None)
                if node:
                    node["risk_score"] = max(0, node["risk_score"] - stored["risk_score"])
                    # Remove this incident from the incidents list
                    node["incidents"] = [
                        i for i in node.get("incidents", [])
                        if i["title"] != stored["title"]
                    ]
                    # Update latest_incident to the next most recent one
                    remaining = node.get("incidents", [])
                    node["latest_incident"] = remaining[-1]["title"] if remaining else None
                    print(f"RESOLVED: {ticket_id} — risk -{stored['risk_score']} on {stored['service_id']}")
            continue

        # ── Skip already-processed active tickets ───────────────
        if ticket_id in synced_ticket_ids or ticket_id in resolved_ticket_ids:
            continue
        synced_ticket_ids.add(ticket_id)

        service_id = incident["service"]
        parsed_description={}
        raw_desc = incident["description"].strip()
        print("RAW DESCRIPTION:")
        print(raw_desc)

        # Try YAML first
        try:
            parsed_description = yaml.safe_load(raw_desc) or {}
        except Exception:
            pass

        # Fallback: regex-based parsing for loose formatting
        if not isinstance(parsed_description, dict) or not parsed_description:
            parsed_description = _parse_description_fallback(raw_desc)
            print("Used fallback parser:", parsed_description)


        risk_score = severity_map.get(
            incident["severity"],
            10
        )

        # Ensure the service node exists
        _ensure_node(service_id, "service", existing_ids)

        existing_node = next(
            (
                node for node in graph_data["nodes"]
                if node["id"] == service_id
            ),
            None
        )
        
        # Safety check - this should never be None after _ensure_node, but be defensive
        if not existing_node:
            print(f"ERROR: Node {service_id} not found after _ensure_node call")
            continue
            
        existing_node["risk_score"] += risk_score
        existing_node["latest_incident"] = incident["title"]

        # Track contribution — including which nodes this ticket created
        created_nodes = [nid for nid in [service_id] if nid not in existing_ids]
        ticket_risk_map[ticket_id] = {
            "service_id": service_id,
            "risk_score": risk_score,
            "title": incident["title"],
            "created_node_ids": created_nodes,
            "created_edges": [],
        }
        
        if "incidents" not in existing_node:
            existing_node["incidents"]=[]  # type: ignore

        # Check if this incident already exists to prevent duplicates
        incident_exists = any(
            inc["title"] == incident["title"] and inc["severity"] == incident["severity"]
            for inc in existing_node["incidents"]
        )
        
        if not incident_exists:
            existing_node["incidents"].append({  # type: ignore
                "title":incident["title"],
                "severity":incident["severity"]
            })
        else:
            print(f"SKIPPED duplicate incident: {incident['title']} on {service_id}")

        project_id = parsed_description.get("project") if isinstance(parsed_description, dict) else None

        if project_id:
            # Create the project node if it doesn't exist
            _ensure_node(project_id, "project", existing_ids)

            existing_edge = next(
                (
                    edge for edge in graph_data["edges"]
                    if edge["source"]==project_id
                    and edge["target"]==service_id
                ),
                None
            )
            if not existing_edge:
                print(
                    "ADDING PROJECT EDGE:",
                    project_id,
                    "->",
                    service_id
                )
                new_edge = {
                    "source": project_id,
                    "target": service_id,
                    "label": "depends_on"
                }
                graph_data["edges"].append(new_edge)
                ticket_risk_map[ticket_id]["created_edges"].append(new_edge)

        # Handle owner_team from YAML description
        owner_team = parsed_description.get("owner_team") if isinstance(parsed_description, dict) else None
        if owner_team:
            _ensure_node(owner_team, "team", existing_ids)

            existing_edge = next(
                (
                    edge for edge in graph_data["edges"]
                    if edge["source"]==service_id
                    and edge["target"]==owner_team
                ),
                None
            )
            if not existing_edge:
                print(
                    "ADDING TEAM EDGE:",
                    service_id,
                    "->",
                    owner_team
                )
                new_edge = {
                    "source": service_id,
                    "target": owner_team,
                    "label": "owned_by"
                }
                graph_data["edges"].append(new_edge)
                ticket_risk_map[ticket_id]["created_edges"].append(new_edge)

        dependencies = (
            parsed_description.get("depends_on") or []
        ) if isinstance(parsed_description, dict) else []

        for dependency in dependencies:
            # Ensure dependency node exists
            _ensure_node(dependency, "service", existing_ids)

            existing_edge = next(
                (
                    edge for edge in graph_data["edges"]
                    if edge["source"]==service_id
                    and edge["target"]==dependency
                ),
                None
            )
            if not existing_edge:
                print(
                    "ADDING DEPENDENCY EDGE:",
                    service_id,
                    "->",
                    dependency
                )
                new_edge = {
                    "source": service_id,
                    "target": dependency,
                    "label": "depends_on"
                }
                graph_data["edges"].append(new_edge)
                ticket_risk_map[ticket_id]["created_edges"].append(new_edge)
        print("FINAL EDGES:")
        print(graph_data["edges"])

    save_graph_data()

    resolved_count = len(resolved_ticket_ids)
    active_count = len(synced_ticket_ids) - resolved_count

    return {
        "message": "Jira incidents synced successfully",
        "active_incidents": active_count,
        "resolved_incidents": resolved_count,
    }


# ─── Chat Endpoint ─────────────────────────────────────────────

@app.post("/chat")
def chat(request: ChatRequest):
    result = process_chat_message(request.message)
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
