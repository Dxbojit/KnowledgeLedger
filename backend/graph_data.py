import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "graph_data.json")


def load_graph_data():
    """Load graph data from JSON file, or return empty graph if file doesn't exist."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"nodes": [], "edges": []}


def save_graph_data():
    """Persist current graph_data to disk."""
    with open(DATA_FILE, "w") as f:
        json.dump(graph_data, f, indent=2)


graph_data = load_graph_data()