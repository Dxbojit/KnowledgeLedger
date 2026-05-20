"""
Analysis functions for the Enterprise AI Management System.
Each function reads graph_data and/or team_data to answer specific question types.
"""

from graph_data import graph_data
from team_data import team_data
from risk_engine import propagate_risk


# ─── 1. Risk Analysis ─────────────────────────────────────────────

def get_high_risk_projects(threshold=50):
    """Find all projects at or above a risk threshold."""
    nodes = propagate_risk()
    edges = graph_data["edges"]

    high_risk = []
    for node in nodes:
        if node["type"] == "project" and node["risk_score"] >= threshold:
            # Find services this project depends on
            deps = [
                next((n["label"] for n in nodes if n["id"] == e["target"]), e["target"])
                for e in edges
                if e["source"] == node["id"]
            ]
            high_risk.append({
                "id": node["id"],
                "label": node["label"],
                "risk_score": node["risk_score"],
                "dependencies": deps,
                "latest_incident": node.get("latest_incident", "None")
            })

    # Also include high-risk services
    high_risk_services = []
    for node in nodes:
        if node["type"] == "service" and node["risk_score"] >= threshold:
            high_risk_services.append({
                "id": node["id"],
                "label": node["label"],
                "risk_score": node["risk_score"],
                "latest_incident": node.get("latest_incident", "None")
            })

    return {
        "high_risk_projects": high_risk,
        "high_risk_services": high_risk_services,
        "threshold": threshold,
        "total_projects": len([n for n in nodes if n["type"] == "project"]),
        "total_services": len([n for n in nodes if n["type"] == "service"])
    }


# ─── 2. Impact Analysis ───────────────────────────────────────────

def get_impact_analysis(node_id):
    """If node X fails, what is affected? (Reverse traversal — who depends on X)"""
    nodes = propagate_risk()
    edges = graph_data["edges"]

    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        return {"error": f"Node '{node_id}' not found"}

    # Reverse BFS — find all nodes that depend on this node
    affected = []
    visited = set()

    def reverse_traverse(nid):
        if nid in visited:
            return
        visited.add(nid)

        # Find all edges where target == nid (i.e., someone depends on nid)
        incoming = [e for e in edges if e["target"] == nid and e["label"] == "depends_on"]
        for edge in incoming:
            source_node = next((n for n in nodes if n["id"] == edge["source"]), None)
            if source_node and source_node["id"] != node_id:
                affected.append({
                    "id": source_node["id"],
                    "label": source_node["label"],
                    "type": source_node["type"],
                    "risk_score": source_node["risk_score"],
                    "dependency_chain": f"{source_node['label']} → depends_on → {nid}"
                })
            reverse_traverse(edge["source"])

    reverse_traverse(node_id)

    return {
        "failed_node": target_node["label"],
        "failed_node_type": target_node["type"],
        "affected_nodes": affected,
        "affected_count": len(affected),
        "severity": "CRITICAL" if len(affected) >= 3 else "HIGH" if len(affected) >= 1 else "LOW"
    }


# ─── 3. Root Cause Analysis ───────────────────────────────────────

def get_root_cause(node_id):
    """What is causing node X to have issues? (Forward DFS along dependencies)"""
    nodes = propagate_risk()
    edges = graph_data["edges"]

    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        return {"error": f"Node '{node_id}' not found"}

    # Forward DFS — follow dependencies and collect incidents
    causes = []
    dependency_chain = []
    visited = set()

    def forward_traverse(nid, depth=0):
        if nid in visited:
            return
        visited.add(nid)

        outgoing = [e for e in edges if e["source"] == nid and e["label"] == "depends_on"]
        for edge in outgoing:
            dep_node = next((n for n in nodes if n["id"] == edge["target"]), None)
            if not dep_node:
                continue

            dependency_chain.append({
                "from": nid,
                "to": dep_node["id"],
                "label": dep_node["label"],
                "depth": depth + 1
            })

            if dep_node.get("latest_incident"):
                causes.append({
                    "node_id": dep_node["id"],
                    "node_label": dep_node["label"],
                    "incident": dep_node["latest_incident"],
                    "risk_score": dep_node["risk_score"],
                    "depth": depth + 1,
                    "all_incidents": dep_node.get("incidents", [])
                })

            forward_traverse(dep_node["id"], depth + 1)

    forward_traverse(node_id)

    return {
        "target_node": target_node["label"],
        "target_risk_score": target_node["risk_score"],
        "root_causes": causes,
        "dependency_chain": dependency_chain,
        "cause_count": len(causes)
    }


# ─── 4. Skills Search ─────────────────────────────────────────────

def find_skilled_members(skills_needed):
    """Find team members who have the requested skills."""
    members = team_data.get("members", [])
    skills_lower = [s.lower() for s in skills_needed]

    results = []
    for member in members:
        member_skills_lower = [s.lower() for s in member.get("skills", [])]
        matched = [s for s in skills_lower if s in member_skills_lower]

        if matched:
            results.append({
                "name": member["name"],
                "role": member.get("role", "Unknown"),
                "team": member.get("team", "Unknown"),
                "matched_skills": matched,
                "all_skills": member.get("skills", []),
                "match_percentage": round(len(matched) / len(skills_lower) * 100)
            })

    # Sort by match percentage (best matches first)
    results.sort(key=lambda x: x["match_percentage"], reverse=True)

    return {
        "searched_skills": skills_needed,
        "matches": results,
        "match_count": len(results),
        "total_members": len(members)
    }


# ─── 5. Risk Mitigation ───────────────────────────────────────────

def get_risk_mitigation_context(node_id):
    """Gather context for AI-powered risk mitigation suggestions."""
    nodes = propagate_risk()
    edges = graph_data["edges"]
    members = team_data.get("members", [])

    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        return {"error": f"Node '{node_id}' not found"}

    # Get dependencies
    deps = []
    for edge in edges:
        if edge["source"] == node_id:
            dep_node = next((n for n in nodes if n["id"] == edge["target"]), None)
            if dep_node:
                deps.append(dep_node)

    # Get owner team + members
    owner_edge = next(
        (e for e in edges if e["source"] == node_id and e["label"] == "owned_by"),
        None
    )
    team_members = []
    if owner_edge:
        team_members = [m for m in members if m.get("team") == owner_edge["target"]]

    # Get incidents
    incidents = target_node.get("incidents", [])

    return {
        "node": target_node,
        "dependencies": deps,
        "incidents": incidents,
        "team_members": team_members,
        "owner_team": owner_edge["target"] if owner_edge else "Unknown"
    }


# ─── 6. Executive Summary ─────────────────────────────────────────

def get_executive_summary():
    """Generate an overall summary of the system status."""
    nodes = propagate_risk()
    edges = graph_data["edges"]
    members = team_data.get("members", [])

    projects = [n for n in nodes if n["type"] == "project"]
    services = [n for n in nodes if n["type"] == "service"]
    teams = [n for n in nodes if n["type"] == "team"]

    high_risk_projects = [p for p in projects if p["risk_score"] >= 50]
    high_risk_services = [s for s in services if s["risk_score"] >= 50]
    critical_services = [s for s in services if s["risk_score"] >= 80]

    all_incidents = []
    for node in nodes:
        for inc in node.get("incidents", []):
            all_incidents.append({
                "title": inc["title"],
                "severity": inc["severity"],
                "service": node["label"]
            })

    # Find most connected node (highest dependency count)
    dependency_counts = {}
    for edge in edges:
        if edge["label"] == "depends_on":
            target = edge["target"]
            dependency_counts[target] = dependency_counts.get(target, 0) + 1

    most_critical_dep = None
    if dependency_counts:
        critical_id = max(dependency_counts, key=dependency_counts.get)
        critical_node = next((n for n in nodes if n["id"] == critical_id), None)
        if critical_node:
            most_critical_dep = {
                "label": critical_node["label"],
                "dependents": dependency_counts[critical_id],
                "risk_score": critical_node["risk_score"]
            }

    return {
        "total_projects": len(projects),
        "total_services": len(services),
        "total_teams": len(teams),
        "total_members": len(members),
        "high_risk_projects": [{"label": p["label"], "risk_score": p["risk_score"]} for p in high_risk_projects],
        "high_risk_services": [{"label": s["label"], "risk_score": s["risk_score"]} for s in high_risk_services],
        "critical_services": [{"label": s["label"], "risk_score": s["risk_score"]} for s in critical_services],
        "active_incidents": all_incidents,
        "incident_count": len(all_incidents),
        "most_critical_dependency": most_critical_dep,
        "overall_health": "CRITICAL" if len(critical_services) > 0
            else "AT RISK" if len(high_risk_services) > 0
            else "HEALTHY"
    }
