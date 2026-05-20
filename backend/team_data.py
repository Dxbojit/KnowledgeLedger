import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "team_data.json")


def load_team_data():
    """Load team data from JSON file, or return empty structure if file doesn't exist."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"members": []}


def save_team_data():
    """Persist current team_data to disk."""
    with open(DATA_FILE, "w") as f:
        json.dump(team_data, f, indent=2)


team_data = load_team_data()
# Loaded from team_data.json on startup
