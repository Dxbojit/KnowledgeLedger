<div align="center">

# 🧠 Knowledge Ledger

### Enterprise AI Risk Intelligence & Dependency Management Platform

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-000000?style=flat-square&logo=next.js)](https://nextjs.org/)
[![Gemini AI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-4285F4?style=flat-square&logo=google)](https://aistudio.google.com/)
[![Jira](https://img.shields.io/badge/Integrations-Jira-0052CC?style=flat-square&logo=jira)](https://www.atlassian.com/software/jira)

</div>

---

## 📌 What is Knowledge Ledger?

**Knowledge Ledger** is an AI-powered enterprise management platform that provides real-time visibility into your organisation's project risks, system dependencies, and team capabilities — all in one interactive graph-based dashboard.

Built for engineering leaders and project managers who need to answer questions like:
- *"Which services are at high risk right now?"*
- *"What happens if the Payment API goes down?"*
- *"Who on my team can fix a Kubernetes issue?"*
- *"What is causing Project Atlas to be at risk?"*

Knowledge Ledger answers all of this — in plain English — powered by Gemini AI.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🗺️ **Live Dependency Graph** | Interactive graph visualising services, projects, and teams pulled directly from Jira |
| ⚡ **Risk Propagation Engine** | Automatically calculates and propagates risk scores across the entire dependency chain |
| 🤖 **AI Chat Assistant** | Natural language Q&A powered by Gemini 2.5 Flash — ask anything about your system health |
| 🔗 **Jira Integration** | One-click sync pulls all active and resolved incidents from your Jira workspace |
| 📊 **Executive Summary** | At-a-glance dashboard of critical services, incident counts, and overall system health |
| 👥 **Team & Skills Registry** | Searchable team member registry with skill matching for rapid incident response |
| 🔍 **Impact Analysis** | Blast-radius analysis — see which systems are affected if a node fails |
| 🌱 **Root Cause Tracing** | Trace the dependency chain to identify what's causing elevated risk |

---

## 🏗️ Architecture Overview

```
knowledge-ledger/
├── backend/                  # FastAPI Python backend
│   ├── main.py               # API routes and Jira sync logic
│   ├── ai_engine.py          # Gemini AI integration with caching & retry
│   ├── chat_router.py        # Intent detection & chat routing
│   ├── analysis_functions.py # Risk, impact, root cause, skills analysis
│   ├── risk_engine.py        # Risk propagation across dependency graph
│   ├── jira_service.py       # Jira REST API client + ADF parser
│   ├── graph_data.py         # Graph state loader/saver
│   ├── team_data.py          # Team data loader/saver
│   ├── graph_data.json       # Persisted graph (auto-generated on sync)
│   ├── team_data.json        # Team members data
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment variable template
│
└── frontend/
    └── my-app/               # Next.js 16 frontend
        ├── app/
        │   ├── page.js       # Main dashboard (graph, chat, team management)
        │   ├── layout.js     # Root layout with font & metadata
        │   └── globals.css   # Global styles & design system
        └── package.json
```

### Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 16, React 19, ReactFlow, React Markdown |
| **Backend** | FastAPI (Python), Uvicorn |
| **AI Engine** | Google Gemini 2.5 Flash via REST API |
| **Data Source** | Atlassian Jira REST API v3 |
| **Persistence** | JSON file-based (graph_data.json, team_data.json) |
| **Styling** | Vanilla CSS with glassmorphism & dark mode |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/graph` | Get full graph with risk-propagated nodes and edges |
| `GET` | `/ai-analysis/{node_id}` | AI-generated risk explanation for a node |
| `POST` | `/sync-incidents` | Rebuild graph from live Jira data |
| `POST` | `/chat` | Send a message to the AI chat assistant |
| `GET` | `/summary` | Executive summary of system health |
| `GET` | `/teams` | Get all team members |
| `POST` | `/teams/member` | Add or update a team member |
| `GET` | `/teams/skills/{skill}` | Find team members by skill |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.9+** and **pip**
- **Node.js 18+** and **npm**
- A **Jira** account with API access
- A **Gemini API key** (free — get one at [aistudio.google.com](https://aistudio.google.com/))

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/your-username/knowledge-ledger.git
cd knowledge-ledger
```

---

### Step 2 — Configure the Backend Environment

```bash
# Copy the environment template
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in your credentials:

```env
JIRA_BASE_URL=https://your-workspace.atlassian.net
EMAIL=your-email@example.com
API_TOKEN=your_jira_api_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

> **Get your Jira API Token:** [id.atlassian.com → Security → API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
>
> **Get your Gemini API Key (free):** [aistudio.google.com](https://aistudio.google.com/)

---

### Step 3 — Run the Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
uvicorn main:app --reload --port 8000
```

The backend will be available at **http://localhost:8000**

You can explore the interactive API docs at **http://localhost:8000/docs**

---

### Step 4 — Run the Frontend

Open a **new terminal window** (keep the backend running):

```bash
cd frontend/my-app

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be available at **http://localhost:3000**

---

### Step 5 — Sync Your Jira Data

Once both servers are running:

1. Open **http://localhost:3000** in your browser
2. Click the **"Sync Jira"** button in the dashboard to pull your live incident data
3. The dependency graph will populate automatically
4. Use the **AI Chat** panel to ask questions about your system

> **Jira Ticket Format:** For best results, structure your Jira ticket descriptions in YAML format:
> ```yaml
> project: project-name
> service: service-name
> owner_team: team-name
> depends_on:
>   - dependency-service-1
>   - dependency-service-2
> ```

---

## 📄 License

This project was built as part of a hackathon submission. See [HACKATHON_PROJECT_REVIEW.md](./HACKATHON_PROJECT_REVIEW.md) for the full project review and design decisions.
