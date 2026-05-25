import os
import logging
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

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
        logger.error("Jira API Error: Status %d — %s", response.status_code, response.text)
        return []

    data = response.json()

    # Check if 'issues' key exists in response
    if "issues" not in data:
        logger.error("Jira API Response missing 'issues' key: %s", data)
        return []

    issues = []
    for issue in data["issues"]:
        fields = issue["fields"]

        description_text = ""

        description_data = fields.get("description")

        if description_data:
            try:
                def _extract_text(node: dict) -> str:
                    """Recursively walk an Atlassian Document Format node tree
                    and collect all text leaves, preserving line breaks.

                    Key ADF node types:
                      doc → paragraph* / bulletList / orderedList
                      bulletList → listItem+ → paragraph → text
                      hardBreak  → void element (no children), represents Shift+Enter

                    The hardBreak MUST be handled first because it has no content
                    children — the old 'if joined:' guard was silently returning ""
                    for it, smashing adjacent lines like "project-bara" and
                    "service: bara-service" into "project-baraservice: bara-service".
                    """
                    node_type = node.get("type")

                    # ── Void nodes ──────────────────────────────────────────
                    if node_type == "hardBreak":
                        return "\n"          # Shift+Enter in Jira editor
                    if node_type == "text":
                        return node.get("text", "")

                    # ── Container nodes ─────────────────────────────────────
                    parts = []
                    for child in node.get("content", []):
                        child_text = _extract_text(child)
                        if child_text:
                            parts.append(child_text)

                    # Append a newline after every block-level container so
                    # YAML field lines stay properly separated.
                    block_types = {"paragraph", "listItem", "bulletList",
                                   "orderedList", "heading", "blockquote", "codeBlock"}
                    joined = "".join(parts)
                    if node_type in block_types and joined:
                        return joined + "\n"
                    return joined

                description_text = _extract_text(description_data).strip()

            except Exception as e:
                logger.warning("Description parse failed: %s", e)

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
    logger.debug("Parsed %d issues from Jira", len(issues))
    return issues