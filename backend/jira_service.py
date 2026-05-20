import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv(override=True)

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://aimanagementsystem.atlassian.net")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")

def fetch_jira_issues():
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"

    query = {
        "jql": "project IS NOT EMPTY ORDER BY created DESC",
        "maxResults":20,
        "fields": "summary,priority,labels,description,status"
    }

    response = requests.get(
        url,
        params=query,
        auth=HTTPBasicAuth(EMAIL, API_TOKEN),
        headers={"Accept": "application/json"}
    )

    # Check if request was successful
    if response.status_code != 200:
        print(f"JIRA API Error: Status {response.status_code}")
        print(f"Response: {response.text}")
        return []

    data = response.json()

    # Check if 'issues' key exists in response
    if "issues" not in data:
        print(f"JIRA API Response missing 'issues' key: {data}")
        return []

    issues = []
    for issue in data["issues"]:
        fields = issue["fields"]

        description_text = ""

        description_data = fields.get("description")

        if description_data:

            try:

                for block in description_data.get("content", []):

                    for item in block.get("content", []):

                        description_text += (
                            item.get("text", "") + "\n"
                        )

            except Exception as e:

                print(
                    "Description parse failed:",
                    e
                )

        issues.append({
            "ticket_id": issue["key"],

            "title": fields["summary"],

            "description": description_text,

            "severity": (
                fields["priority"]["name"].upper()
                if fields.get("priority")
                else "LOW"
            ),

            "service": (
                fields["labels"][0]
                if fields.get("labels")
                and len(fields["labels"]) > 0
                else None
            ),
            "status": fields.get("status", {}).get("name", "Unknown"),
            "is_done": fields.get("status", {}).get("statusCategory", {}).get("key", "") == "done"
        })
    print("PARSED ISSUES:", issues)
    return issues