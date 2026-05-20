"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import ReactFlow from "reactflow";
import "reactflow/dist/style.css";

const API = "http://127.0.0.1:8000";

const SUGGESTED_QUESTIONS = [
  "Which projects are at high risk?",
  "What happens if payment-api fails?",
  "Who knows Python and Spring Boot?",
  "What is causing auth-service to fail?",
  "Give me an executive summary",
  "How to mitigate risk for inventory-service?",
];

export default function Home() {
  // ─── Graph State ──────────────────────────────────────────
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState("");

  // ─── Chat State ───────────────────────────────────────────
  const [activeTab, setActiveTab] = useState("chat");
  const [chatMessages, setChatMessages] = useState([
    { role: "system", text: "Enterprise AI Assistant ready. Ask me anything about your systems." },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);

  // ─── Dashboard State ──────────────────────────────────────
  const [summary, setSummary] = useState(null);
  const [showIncidentModal, setShowIncidentModal] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [toast, setToast] = useState(null);
  const [isPanelOpen, setIsPanelOpen] = useState(true);
  const [showRiskLegend, setShowRiskLegend] = useState(false);

  const chatEndRef = useRef(null);
  const chatInputRef = useRef(null);

  // ─── Load Graph ───────────────────────────────────────────
  const loadGraph = useCallback(() => {
    fetch(`${API}/graph`)
      .then((res) => res.json())
      .then((data) => {
        const projects = data.nodes.filter((n) => n.type === "project");
        const services = data.nodes.filter((n) => n.type === "service");
        const teams = data.nodes.filter((n) => n.type === "team");
        const others = data.nodes.filter((n) => !["project", "service", "team"].includes(n.type));

        const layoutPositions = {};
        const xSpacing = 300;
        const centerX = (count) => Math.max(50, (900 - count * xSpacing) / 2);

        projects.forEach((n, i) => {
          layoutPositions[n.id] = { x: centerX(projects.length) + i * xSpacing, y: 60 };
        });
        services.forEach((n, i) => {
          layoutPositions[n.id] = { x: centerX(services.length) + i * xSpacing, y: 280 };
        });
        teams.forEach((n, i) => {
          layoutPositions[n.id] = { x: centerX(teams.length) + i * xSpacing, y: 480 };
        });
        others.forEach((n, i) => {
          layoutPositions[n.id] = { x: centerX(others.length) + i * xSpacing, y: 650 };
        });

        const getNodeStyle = (node) => {
          if (node.type === "project") {
            return {
              padding: "14px 20px",
              borderRadius: 14,
              border: "2px solid #f59e0b",
              background: "linear-gradient(135deg, #1e3a5f, #0f172a)",
              color: "#f8fafc",
              fontWeight: 700,
              fontSize: 13,
              minWidth: 170,
              textAlign: "center",
              boxShadow: "0 0 24px rgba(245, 158, 11, 0.3)",
            };
          }
          if (node.type === "team") {
            return {
              padding: "8px 14px",
              borderRadius: 10,
              border: "1px dashed #64748b",
              background: "#1e293b",
              color: "#cbd5e1",
              fontSize: 11,
            };
          }
          const risk = node.risk_score;
          return {
            padding: "10px 16px",
            borderRadius: 10,
            border: `1px solid ${risk >= 80 ? "#ef4444" : risk >= 50 ? "#f59e0b" : "#334155"}`,
            background: risk >= 80 ? "rgba(239,68,68,0.15)" : risk >= 50 ? "rgba(245,158,11,0.12)" : "#1e293b",
            color: "#e2e8f0",
            fontSize: 12,
          };
        };

        const flowNodes = data.nodes.map((node) => ({
          id: node.id,
          data: {
            label:
              node.type === "project"
                ? `📁 ${node.label}\nRisk: ${node.risk_score}`
                : node.type === "team"
                ? `👥 ${node.label}`
                : `${node.label}\n⚡ Risk: ${node.risk_score}`,
            fullData: node,
          },
          position: layoutPositions[node.id] || { x: 0, y: 0 },
          style: getNodeStyle(node),
        }));

        const flowEdges = data.edges.map((edge, index) => ({
          id: `e-${index}`,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          animated: true,
          style: { stroke: "#475569", strokeWidth: 1.5 },
          labelStyle: { fill: "#64748b", fontSize: 10 },
        }));

        setNodes(flowNodes);
        setEdges(flowEdges);
      });
  }, []);

  // ─── Load Summary ─────────────────────────────────────────
  const loadSummary = useCallback(() => {
    fetch(`${API}/summary`)
      .then((res) => res.json())
      .then(setSummary)
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadGraph();
    loadSummary();
  }, [loadGraph, loadSummary]);

  // ─── Scroll chat to bottom ────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, isChatLoading]);

  // ─── AI Node Analysis ─────────────────────────────────────
  const fetchAIAnalysis = async (nodeId) => {
    setAiAnalysis("loading");
    try {
      const res = await fetch(`${API}/ai-analysis/${nodeId}`);
      const data = await res.json();
      setAiAnalysis(data.error ? `❌ ${data.error}` : data.analysis || "No analysis returned.");
    } catch {
      setAiAnalysis("❌ Could not reach backend.");
    }
  };

  // ─── Chat Send ────────────────────────────────────────────
  const sendChatMessage = async (message) => {
    if (!message.trim() || isChatLoading) return;

    const userMsg = { role: "user", text: message };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setIsChatLoading(true);

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      setChatMessages((prev) => [
        ...prev,
        { role: "ai", text: data.reply, intent: data.intent },
      ]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        { role: "ai", text: "❌ Could not reach the AI backend. Is the server running?" },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // ─── Sync Jira ────────────────────────────────────────────
  const syncJira = async () => {
    setIsSyncing(true);
    try {
      await fetch(`${API}/sync-incidents`, { method: "POST" });
      loadGraph();
      loadSummary();
      showToast("success", "Jira synced successfully", "Graph and metrics updated");
    } catch {
      showToast("error", "Sync failed", "Could not reach backend");
    } finally {
      setIsSyncing(false);
    }
  };

  // ─── Toast ────────────────────────────────────────────────
  const showToast = (type, message, sub) => {
    setToast({ type, message, sub, id: Date.now() });
    setTimeout(() => setToast(null), 3500);
  };

  // ─── Get health class ────────────────────────────────────
  const healthClass = summary
    ? summary.overall_health === "CRITICAL"
      ? "critical"
      : summary.overall_health === "AT RISK"
      ? "at-risk"
      : "healthy"
    : "healthy";

  // ─── Render ───────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* ═══ Top Bar ═══ */}
      <div className="top-bar">
        <div className="top-bar-left">
          <div className="logo-section">
            <div className="app-logo">
              <div className="app-logo-icon">⚡</div>
              Knowledge Ledger
            </div>
            <div className="risk-info-wrapper">
              <button
                className="risk-info-trigger"
                onClick={() => setShowRiskLegend((prev) => !prev)}
                onMouseEnter={() => setShowRiskLegend(true)}
                onMouseLeave={() => setShowRiskLegend(false)}
                aria-label="Show Risk Scale Legend"
              >
                <span className="info-icon">i</span>
                <span className="info-text">Risk Categories</span>
              </button>
              {showRiskLegend && (
                <div className="risk-legend-popover">
                  <div className="risk-legend-header">Risk Score Scale</div>
                  <div className="risk-legend-divider"></div>
                  <div className="risk-legend-item">
                    <span className="risk-badge-dot low"></span>
                    <span className="risk-legend-range">&lt; 50</span>
                    <span className="risk-legend-label low">risk low</span>
                  </div>
                  <div className="risk-legend-item">
                    <span className="risk-badge-dot moderate"></span>
                    <span className="risk-legend-range">50 - 100</span>
                    <span className="risk-legend-label moderate">risk moderate</span>
                  </div>
                  <div className="risk-legend-item">
                    <span className="risk-badge-dot high"></span>
                    <span className="risk-legend-range">&gt; 100</span>
                    <span className="risk-legend-label high">high risk</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {summary && (
            <div className="top-bar-metrics">
              <div className={`metric-pill ${healthClass}`}>
                <span className="value">{summary.overall_health}</span>
              </div>
              <div className="metric-pill">
                📁 <span className="value">{summary.total_projects}</span> Projects
              </div>
              <div className="metric-pill">
                ⚙️ <span className="value">{summary.total_services}</span> Services
              </div>
              <div className={`metric-pill ${summary.incident_count > 0 ? "warning" : ""}`}>
                🔥 <span className="value">{summary.incident_count}</span> Incidents
              </div>
              <div className="metric-pill">
                👥 <span className="value">{summary.total_members}</span> Members
              </div>
            </div>
          )}
        </div>

        <div className="top-bar-actions">
          <button className="btn" onClick={() => setShowIncidentModal(true)}>
            📝 Raise Incident
          </button>
          <button className="btn btn-success" onClick={syncJira} disabled={isSyncing}>
            {isSyncing ? <><span className="btn-spinner" /> Syncing...</> : "🔄 Sync Jira"}
          </button>
        </div>
      </div>

      {/* ═══ Main Content ═══ */}
      <div className="main-content">
        {/* ── Graph ── */}
        <div className="graph-panel">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={(_, node) => {
              setSelectedNode(node.data.fullData);
              setActiveTab("details");
              fetchAIAnalysis(node.id);
            }}
            fitView
            style={{ background: "#0a0e1a" }}
          />
        </div>

        {/* ── Panel Toggle ── */}
        <button
          className="panel-toggle"
          onClick={() => setIsPanelOpen(!isPanelOpen)}
          title={isPanelOpen ? 'Hide panel' : 'Show panel'}
        >
          {isPanelOpen ? '›' : '‹'}
        </button>

        {/* ── Right Panel ── */}
        <div className={`right-panel ${isPanelOpen ? '' : 'collapsed'}`}>
          {/* Tab Bar */}
          <div className="tab-bar">
            <button
              className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
              onClick={() => setActiveTab("chat")}
            >
              🤖 AI Chat
            </button>
            <button
              className={`tab-btn ${activeTab === "details" ? "active" : ""}`}
              onClick={() => setActiveTab("details")}
            >
              📊 Node Details
            </button>
          </div>

          {/* ── Chat Tab ── */}
          {activeTab === "chat" && (
            <div className="chat-panel">
              <div className="chat-messages">
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`chat-bubble ${msg.role}`}>
                    {msg.intent && (
                      <div className="intent-badge">{msg.intent.replace("_", " ")}</div>
                    )}
                    <div>{msg.text}</div>
                  </div>
                ))}
                {isChatLoading && (
                  <div className="typing-indicator">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Suggested Questions */}
              {!isChatLoading && (
                <div className="suggested-questions">
                  <div className="label">Try asking</div>
                  {SUGGESTED_QUESTIONS.map((q, i) => (
                    <button
                      key={i}
                      className="suggestion-chip"
                      onClick={() => sendChatMessage(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {/* Input */}
              <div className="chat-input-area">
                <div className="chat-input-wrapper">
                  <input
                    ref={chatInputRef}
                    className="chat-input"
                    placeholder="Ask about risks, dependencies, team skills..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        sendChatMessage(chatInput);
                      }
                    }}
                    disabled={isChatLoading}
                  />
                  <button
                    className="chat-send-btn"
                    onClick={() => sendChatMessage(chatInput)}
                    disabled={!chatInput.trim() || isChatLoading}
                  >
                    ➤
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── Details Tab ── */}
          {activeTab === "details" && (
            <div className="node-details">
              {selectedNode ? (
                <div className="animate-fade-in">
                  <div className="node-header">
                    <div className={`node-type-badge ${selectedNode.type}`}>
                      {selectedNode.type}
                    </div>
                    <div className="node-title">{selectedNode.label}</div>
                  </div>

                  {/* Risk Bar */}
                  <div
                    className={`risk-bar ${
                      selectedNode.risk_score >= 80
                        ? "critical"
                        : selectedNode.risk_score >= 50
                        ? "moderate"
                        : "low"
                    }`}
                  >
                    <div>
                      <div
                        className="risk-label"
                        style={{
                          color:
                            selectedNode.risk_score >= 80
                              ? "#ef4444"
                              : selectedNode.risk_score >= 50
                              ? "#f59e0b"
                              : "#10b981",
                        }}
                      >
                        {selectedNode.risk_score >= 80
                          ? "CRITICAL RISK"
                          : selectedNode.risk_score >= 50
                          ? "MODERATE RISK"
                          : "LOW RISK"}
                      </div>
                    </div>
                    <div
                      className="risk-score"
                      style={{
                        color:
                          selectedNode.risk_score >= 80
                            ? "#ef4444"
                            : selectedNode.risk_score >= 50
                            ? "#f59e0b"
                            : "#10b981",
                      }}
                    >
                      {selectedNode.risk_score}
                    </div>
                  </div>

                  {/* Connections */}
                  {edges.filter((e) => e.source === selectedNode.id).length > 0 && (
                    <div className="detail-section">
                      <div className="detail-section-title">Dependencies</div>
                      {edges
                        .filter((e) => e.source === selectedNode.id)
                        .map((e, i) => {
                          const target = nodes.find((n) => n.id === e.target);
                          return (
                            <div key={i} className="detail-item">
                              <span className="arrow">→</span>
                              <span>{e.label}</span>
                              <span className="arrow">→</span>
                              <span style={{ color: "#e2e8f0" }}>
                                {target?.data?.fullData?.label || e.target}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  )}

                  {/* Incidents */}
                  {selectedNode.incidents && selectedNode.incidents.length > 0 && (
                    <div className="detail-section">
                      <div className="detail-section-title">Active Incidents</div>
                      {selectedNode.incidents.map((inc, i) => (
                        <div key={i} className="detail-item">
                          <span>{inc.severity === "HIGH" ? "🔴" : inc.severity === "MEDIUM" ? "🟡" : "🟢"}</span>
                          <span>{inc.title}</span>
                          <span style={{ marginLeft: "auto", fontSize: 10, color: "#64748b" }}>
                            {inc.severity}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* AI Analysis */}
                  <div className="detail-section">
                    <div className="detail-section-title">AI Analysis</div>
                    <div className={`ai-box ${aiAnalysis === "loading" ? "loading" : ""}`}>
                      {aiAnalysis === "loading"
                        ? "Analyzing..."
                        : aiAnalysis || "Click a node to generate analysis."}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-icon">📊</div>
                  <div className="empty-state-text">
                    Click a node on the graph to view its details, dependencies, and AI analysis.
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ═══ Incident Modal ═══ */}
      {showIncidentModal && (
        <div className="modal-overlay" onClick={() => setShowIncidentModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>📝 Raise Jira Incident</h2>
            <p style={{ color: "#94a3b8", fontSize: 13 }}>
              Enter Jira ticket description in this YAML format:
            </p>
            <pre>{`project: project-atlas
service: auth-service
depends_on:
  - payment-api
owner_team: infra-team`}</pre>
            <div className="modal-actions">
              <button
                className="btn btn-primary"
                onClick={() =>
                  window.open(
                    "https://aimanagementsystem.atlassian.net/jira/software/projects/KAN/issues",
                    "_blank"
                  )
                }
              >
                Continue to Jira →
              </button>
              <button className="btn" onClick={() => setShowIncidentModal(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ Toast ═══ */}
      {toast && (
        <div className="toast-container" key={toast.id}>
          <div className={`toast ${toast.type}`} style={{ position: "relative", overflow: "hidden" }}>
            <span className="toast-icon">{toast.type === "success" ? "✓" : "✕"}</span>
            <div className="toast-message">
              {toast.message}
              {toast.sub && <div className="toast-sub">{toast.sub}</div>}
            </div>
            <div className="toast-progress" />
          </div>
        </div>
      )}
    </div>
  );
}
