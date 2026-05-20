import copy
from graph_data import graph_data


def propagate_risk():
    nodes = {
        node["id"]: copy.deepcopy(node)
        for node in graph_data["nodes"]
    }

    # 1. Map dependencies and dependents
    depends_on = {}  # source -> list of targets
    dependents = {}  # target -> list of sources

    for edge in graph_data["edges"]:
        if edge["label"] == "depends_on":
            source = edge["source"]
            target = edge["target"]
            if target in nodes and source in nodes:
                depends_on.setdefault(source, []).append(target)
                dependents.setdefault(target, []).append(source)

    # Helper to find all transitive service nodes in a dependency tree
    def get_all_transitive_services(start_node_id):
        visited = set()
        services = set()
        queue = [start_node_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            if current != start_node_id and nodes[current].get("type") == "service":
                services.add(current)

            for dep in depends_on.get(current, []):
                queue.append(dep)

        return services

    # 2. Compute Proportional Stress Index for Services first
    # A service inherits 20% of the combined risk of any upstream services depending on it
    base_risks = {nid: n.get("risk_score", 0) for nid, n in nodes.items()}

    for node_id, node in nodes.items():
        if node.get("type") == "service":
            upstream_services = [
                src for src in dependents.get(node_id, [])
                if nodes[src].get("type") == "service"
            ]
            if upstream_services:
                inherited_stress = sum(base_risks[src] for src in upstream_services) * 0.20
                node["risk_score"] += int(inherited_stress)

    # 3. Compute Risk for Projects (Proportional Average of entire transitive ecosystem)
    for node_id, node in nodes.items():
        if node.get("type") == "project":
            transitive_services = get_all_transitive_services(node_id)
            if transitive_services:
                total_risk = sum(nodes[svc_id].get("risk_score", 0) for svc_id in transitive_services)
                node["risk_score"] = int(total_risk / len(transitive_services))
            else:
                node["risk_score"] = 0

    return list(nodes.values())