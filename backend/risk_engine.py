import copy
from graph_data import graph_data


def propagate_risk():

    nodes = {
        node["id"]: copy.deepcopy(node)
        for node in graph_data["nodes"]
    }

    for edge in graph_data["edges"]:

        source = edge["source"]
        target = edge["target"]
        relation = edge["label"]

        # Skip if target node doesn't exist
        if target not in nodes:
            continue

        # If project/service depends on risky service
        if relation == "depends_on":

            target_risk = nodes[target]["risk_score"]

            if target_risk > 50:

                nodes[source]["risk_score"] += 40

    return list(nodes.values())