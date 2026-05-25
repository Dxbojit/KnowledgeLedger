"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import ReactFlow from "reactflow";
import "reactflow/dist/style.css";
import ReactMarkdown from "react-markdown";


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
  const [rawNodes, setRawNodes] = useState([]);
  const [rawEdges, setRawEdges] = useState([]);
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
  const [copied, setCopied] = useState(false);

  const chatEndRef = useRef(null);
  const chatInputRef = useRef(null);
  // Stable session ID for ICA conversation continuity
  const sessionIdRef = useRef(typeof crypto !== "undefined" ? crypto.randomUUID() : "session-" + Date.now());

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
          style: {
            ...getNodeStyle(node),
            transition: "opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.25s cubic-bezier(0.4, 0, 0.2, 1), outline 0.25s cubic-bezier(0.4, 0, 0.2, 1), filter 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
          },
        }));

        const flowEdges = data.edges.map((edge, index) => ({
          id: `e-${index}`,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          animated: true,
          style: { stroke: "#475569", strokeWidth: 1.5, transition: "stroke 0.25s ease, stroke-width 0.25s ease, opacity 0.25s ease" },
          labelStyle: { fill: "#64748b", fontSize: 10, transition: "fill 0.25s ease" },
        }));

        setRawNodes(flowNodes);
        setRawEdges(flowEdges);
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

  // ─── Dynamic Selection Highlighting ───────────────────────
  // Three-tier visual hierarchy:
  //   ① SELECTED   — vivid blue neon glow (the clicked node)
  //   ② CONNECTED  — bright indigo glow  (every node reachable in either direction)
  //   ③ UNRELATED  — crushed to 10% opacity + grayscale
  useEffect(() => {
    if (!selectedNode) {
      setNodes(rawNodes);
      setEdges(rawEdges);
      return;
    }

    const selectedId = selectedNode.id;

    // ── Dynamic BFS Bidirectional Traversal ──
    // Builds an adjacency map from all edges (both directions) and performs
    // BFS from the selected node to find every connected node transitively.
    // This works for any graph topology without any hardcoded node IDs.
    const adjacency = {};
    rawEdges.forEach((edge) => {
      if (!adjacency[edge.source]) adjacency[edge.source] = [];
      if (!adjacency[edge.target]) adjacency[edge.target] = [];
      // Add both directions so we traverse upstream AND downstream
      adjacency[edge.source].push(edge.target);
      adjacency[edge.target].push(edge.source);
    });

    const connectedIds = new Set([selectedId]);
    const queue = [selectedId];
    while (queue.length > 0) {
      const current = queue.shift();
      (adjacency[current] || []).forEach((neighbor) => {
        if (!connectedIds.has(neighbor)) {
          connectedIds.add(neighbor);
          queue.push(neighbor);
        }
      });
    }

    // ── Node styles ──
    const updatedNodes = rawNodes.map((node) => {
      const isSelf      = node.id === selectedId;
      const isConnected = !isSelf && connectedIds.has(node.id);

      if (isSelf) {
        // ① SELECTED — bright blue neon ring + strong glow
        const base = node.style.boxShadow || "";
        return {
          ...node,
          style: {
            ...node.style,
            opacity:   1,
            filter:    "none",
            outline:   "2px solid #3b82f6",
            boxShadow: (base ? base + ", " : "") + "0 0 0 4px rgba(59,130,246,0.30), 0 0 32px rgba(59,130,246,0.85)",
            zIndex:    1000,
          },
        };
      }

      if (isConnected) {
        // ② CONNECTED — indigo glow, clearly brighter than the normal state
        const base = node.style.boxShadow || "";
        return {
          ...node,
          style: {
            ...node.style,
            opacity:   1,
            filter:    "none",
            outline:   "2px solid rgba(99,102,241,0.75)",
            boxShadow: (base ? base + ", " : "") + "0 0 0 3px rgba(99,102,241,0.20), 0 0 20px rgba(99,102,241,0.60)",
            zIndex:    990,
          },
        };
      }

      // ③ UNRELATED — recede into the background
      return {
        ...node,
        style: {
          ...node.style,
          opacity:       0.10,
          filter:        "grayscale(80%) brightness(0.6)",
          outline:       "none",
          boxShadow:     "none",
          pointerEvents: "none",
          zIndex:        1,
        },
      };
    });

    // ── Edge styles ──
    const updatedEdges = rawEdges.map((edge) => {
      const touchesSelected = edge.source === selectedId || edge.target === selectedId;
      const bothConnected   = connectedIds.has(edge.source) && connectedIds.has(edge.target);

      if (touchesSelected) {
        // Direct edges from/to selected node — vivid blue, thick
        return {
          ...edge,
          animated:   true,
          style:      { stroke: "#3b82f6", strokeWidth: 2.5, opacity: 1 },
          labelStyle: { fill: "#93c5fd", fontSize: 10, fontWeight: 600 },
        };
      }
      if (bothConnected) {
        // Edges within the connected cluster — indigo, animated
        return {
          ...edge,
          animated:   true,
          style:      { stroke: "#6366f1", strokeWidth: 2, opacity: 0.85 },
          labelStyle: { fill: "#a5b4fc", fontSize: 10 },
        };
      }
      // Edges to unrelated nodes — almost invisible
      return {
        ...edge,
        animated:   false,
        style:      { stroke: "#1e293b", strokeWidth: 1, opacity: 0.04 },
        labelStyle: { fill: "transparent", fontSize: 10 },
      };
    });

    setNodes(updatedNodes);
    setEdges(updatedEdges);
  }, [rawNodes, rawEdges, selectedNode]);

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
        body: JSON.stringify({
          message,
          session_id: sessionIdRef.current,
        }),
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
                    <span className="risk-legend-range">50 - 80</span>
                    <span className="risk-legend-label moderate">risk moderate</span>
                  </div>
                  <div className="risk-legend-item">
                    <span className="risk-badge-dot high"></span>
                    <span className="risk-legend-range">&gt; 80</span>
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
            onPaneClick={() => {
              setSelectedNode(null);
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
                    {msg.role === "ai" ? (
                      <div className="chat-markdown">
                        <ReactMarkdown>{msg.text}</ReactMarkdown>
                      </div>
                    ) : (
                      <div>{msg.text}</div>
                    )}
                  </div>
                ))}
                {isChatLoading && (
                  <div className="typing-indicator">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                )}

                {/* Suggested Questions at the bottom of the conversation */}
                {!isChatLoading && (
                  <div className="suggested-questions animate-fade-in">
                    <div className="label">Try asking</div>
                    <div className="suggestion-chips-container">
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
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

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
                  <div className="node-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div className={`node-type-badge ${selectedNode.type}`}>
                        {selectedNode.type}
                      </div>
                      <div className="node-title">{selectedNode.label}</div>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedNode(null);
                        setActiveTab("chat");
                      }}
                      className="btn"
                      style={{ padding: "4px 8px", fontSize: "11px", borderRadius: "6px" }}
                      title="Clear node selection"
                    >
                      ✕ Close
                    </button>
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
            <div style={{ position: "relative" }}>
              <pre style={{ margin: 0, paddingRight: "48px" }}>{`project: project-atlas
service: auth-service
depends_on:
  - payment-api
owner_team: infra-team`}</pre>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(`project: project-atlas
service: auth-service
depends_on:
  - payment-api
owner_team: infra-team`);
                  setCopied(true);
                  showToast("success", "Copied to clipboard!", "YAML template is ready to paste in Jira");
                  setTimeout(() => setCopied(false), 2000);
                }}
                title="Copy template to clipboard"
                style={{
                  position: "absolute",
                  top: "10px",
                  right: "10px",
                  background: copied ? "rgba(16, 185, 129, 0.15)" : "rgba(255, 255, 255, 0.06)",
                  border: copied ? "1px solid var(--accent-emerald)" : "1px solid rgba(255, 255, 255, 0.12)",
                  borderRadius: "var(--radius-sm)",
                  color: copied ? "var(--accent-emerald)" : "var(--text-secondary)",
                  width: "32px",
                  height: "32px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
                  outline: "none",
                  fontSize: "14px",
                  boxShadow: copied ? "0 0 12px rgba(16, 185, 129, 0.2)" : "none",
                }}
                onMouseEnter={(e) => {
                  if (!copied) {
                    e.currentTarget.style.background = "rgba(59, 130, 246, 0.15)";
                    e.currentTarget.style.borderColor = "var(--accent-blue)";
                    e.currentTarget.style.color = "var(--text-primary)";
                    e.currentTarget.style.boxShadow = "0 0 10px rgba(59, 130, 246, 0.2)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!copied) {
                    e.currentTarget.style.background = "rgba(255, 255, 255, 0.06)";
                    e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.12)";
                    e.currentTarget.style.color = "var(--text-secondary)";
                    e.currentTarget.style.boxShadow = "none";
                  }
                }}
              >
                {copied ? "✓" : "📋"}
              </button>
            </div>
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
