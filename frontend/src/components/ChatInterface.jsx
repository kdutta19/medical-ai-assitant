import React, { useState, useRef, useEffect } from "react";
import { sendQuery } from "../api.js";

// ── Confidence helpers ────────────────────────────────────────────────────────

function confidenceMeta(score, contextUsed) {
  if (!contextUsed || score === 0)
    return { label: "No context", color: "#718096", bg: "#edf2f7" };
  if (score >= 0.75)
    return { label: "High", color: "#276749", bg: "#c6f6d5" };
  if (score >= 0.50)
    return { label: "Medium", color: "#744210", bg: "#fefcbf" };
  return { label: "Low", color: "#742a2a", bg: "#fed7d7" };
}

function confidenceDots(score, contextUsed) {
  if (!contextUsed || score === 0) return "○○○○○";
  const filled = Math.round(score * 5);
  return "●".repeat(filled) + "○".repeat(5 - filled);
}

const ROUTE_COLORS = {
  treatment:  { color: "#1a365d", bg: "#bee3f8" },
  diagnosis:  { color: "#322659", bg: "#e9d8fd" },
  lifestyle:  { color: "#1c4532", bg: "#c6f6d5" },
  general:    { color: "#2d3748", bg: "#e2e8f0" },
};

// ── Inline styles ─────────────────────────────────────────────────────────────

const S = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    maxWidth: "860px",
    margin: "0 auto",
    padding: "0 1rem",
  },
  feed: {
    flex: 1,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "1.25rem",
    padding: "1.25rem 0",
  },
  userRow: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
  },
  assistantRow: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    maxWidth: "82%",
  },
  roleLabel: {
    fontSize: "0.68rem",
    fontWeight: "700",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "#718096",
    marginBottom: "0.3rem",
  },
  userBubble: {
    backgroundColor: "#2b6cb0",
    color: "#fff",
    padding: "0.7rem 1rem",
    borderRadius: "1rem 1rem 0.25rem 1rem",
    lineHeight: "1.6",
    whiteSpace: "pre-wrap",
    maxWidth: "72vw",
    boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
  },
  assistantCard: {
    backgroundColor: "#ffffff",
    borderRadius: "0.25rem 1rem 1rem 1rem",
    boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
    overflow: "hidden",
    width: "100%",
  },
  answerBody: {
    padding: "0.9rem 1.1rem",
    lineHeight: "1.7",
    whiteSpace: "pre-wrap",
    fontSize: "0.95rem",
    color: "#1a202c",
  },
  metaBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: "0.4rem",
    alignItems: "center",
    padding: "0.5rem 1.1rem",
    borderTop: "1px solid #edf2f7",
    backgroundColor: "#f7fafc",
  },
  pill: (color, bg) => ({
    fontSize: "0.68rem",
    fontWeight: "700",
    color,
    backgroundColor: bg,
    padding: "0.2rem 0.55rem",
    borderRadius: "9999px",
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    whiteSpace: "nowrap",
  }),
  sourceToggle: {
    fontSize: "0.7rem",
    color: "#3182ce",
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "0.2rem 0.4rem",
    marginLeft: "auto",
    fontWeight: "600",
  },
  sourcesPanel: {
    borderTop: "1px solid #edf2f7",
    padding: "0.6rem 1.1rem 0.75rem",
    backgroundColor: "#f7fafc",
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
  },
  sourceItem: {
    fontSize: "0.78rem",
    color: "#4a5568",
    lineHeight: "1.4",
    paddingLeft: "0.75rem",
    borderLeft: "2px solid #bee3f8",
  },
  sourceRef: {
    fontSize: "0.7rem",
    color: "#718096",
  },
  disclaimer: {
    fontSize: "0.72rem",
    color: "#a0aec0",
    fontStyle: "italic",
    padding: "0.5rem 1.1rem 0.65rem",
    borderTop: "1px solid #edf2f7",
  },
  errorCard: {
    backgroundColor: "#fff5f5",
    border: "1px solid #fc8181",
    borderRadius: "0.25rem 1rem 1rem 1rem",
    padding: "0.75rem 1rem",
    color: "#c53030",
    fontSize: "0.9rem",
    lineHeight: "1.5",
  },
  loadingCard: {
    backgroundColor: "#ffffff",
    borderRadius: "0.25rem 1rem 1rem 1rem",
    boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
    padding: "0.85rem 1.1rem",
    color: "#718096",
    fontSize: "0.9rem",
    display: "flex",
    gap: "0.3rem",
    alignItems: "center",
  },
  inputArea: {
    display: "flex",
    gap: "0.5rem",
    padding: "0.75rem 0 0.5rem",
    borderTop: "1px solid #e2e8f0",
  },
  textarea: {
    flex: 1,
    padding: "0.7rem 0.9rem",
    borderRadius: "0.5rem",
    border: "1px solid #cbd5e0",
    resize: "none",
    fontSize: "0.93rem",
    fontFamily: "inherit",
    lineHeight: "1.5",
    outline: "none",
    backgroundColor: "#fff",
    transition: "border-color 0.15s",
  },
  sendBtn: (disabled) => ({
    padding: "0.7rem 1.4rem",
    borderRadius: "0.5rem",
    border: "none",
    backgroundColor: disabled ? "#a0aec0" : "#2b6cb0",
    color: "#fff",
    cursor: disabled ? "not-allowed" : "pointer",
    fontWeight: "700",
    fontSize: "0.93rem",
    transition: "background-color 0.15s",
    whiteSpace: "nowrap",
  }),
  footerNote: {
    fontSize: "0.72rem",
    color: "#a0aec0",
    textAlign: "center",
    padding: "0.25rem 0 0.6rem",
  },
};

// ── Sub-components ────────────────────────────────────────────────────────────

function RouteBadge({ category }) {
  if (!category) return null;
  const { color, bg } = ROUTE_COLORS[category] || ROUTE_COLORS.general;
  return <span style={S.pill(color, bg)}>{category}</span>;
}

function ConfidenceBadge({ confidence, contextUsed }) {
  const { label, color, bg } = confidenceMeta(confidence, contextUsed);
  const dots = confidenceDots(confidence, contextUsed);
  const pct = contextUsed ? ` ${Math.round(confidence * 100)}%` : "";
  return (
    <span style={S.pill(color, bg)}>
      {dots} {label}{pct}
    </span>
  );
}

function SourcesSection({ sources }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  return (
    <>
      <div style={S.metaBar}>
        <span style={{ fontSize: "0.7rem", color: "#718096" }}>
          {sources.length} source{sources.length !== 1 ? "s" : ""}
        </span>
        <button style={S.sourceToggle} onClick={() => setOpen((v) => !v)}>
          {open ? "Hide sources ▲" : "Show sources ▼"}
        </button>
      </div>
      {open && (
        <div style={S.sourcesPanel}>
          {sources.map((src, i) => (
            <div key={i} style={S.sourceItem}>
              <div>{src.title}</div>
              {src.reference && src.reference !== src.title && (
                <div style={S.sourceRef}>{src.reference}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function AssistantMessage({ msg }) {
  return (
    <div style={S.assistantRow}>
      <div style={S.roleLabel}>Clinical AI</div>
      {msg.isError ? (
        <div style={S.errorCard}>{msg.text}</div>
      ) : (
        <div style={S.assistantCard}>
          <div style={S.answerBody}>{msg.text}</div>

          <div style={S.metaBar}>
            <RouteBadge category={msg.route_category} />
            <ConfidenceBadge
              confidence={msg.confidence}
              contextUsed={msg.context_used}
            />
          </div>

          <SourcesSection sources={msg.sources} />

          {msg.disclaimer && (
            <div style={S.disclaimer}>{msg.disclaimer}</div>
          )}
        </div>
      )}
    </div>
  );
}

function WelcomeScreen() {
  return (
    <div style={{ textAlign: "center", color: "#718096", marginTop: "4rem", padding: "0 1rem" }}>
      <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>&#9877;</div>
      <p style={{ fontSize: "1.15rem", fontWeight: "700", color: "#2d3748" }}>
        Clinical AI Assistant
      </p>
      <p style={{ fontSize: "0.88rem", marginTop: "0.6rem", maxWidth: "480px", margin: "0.6rem auto 0" }}>
        Ask about clinical guidelines, drug dosing &amp; interactions, diagnostic criteria, and more.
        Answers are grounded in your clinical knowledge base.
      </p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center", marginTop: "1.5rem" }}>
        {[
          "First-line agents for hypertension?",
          "Metformin max daily dose?",
          "HbA1c threshold for diabetes diagnosis?",
          "Risk of ACE inhibitor + ARB combination?",
        ].map((q) => (
          <span
            key={q}
            style={{
              fontSize: "0.78rem",
              color: "#3182ce",
              backgroundColor: "#ebf8ff",
              padding: "0.3rem 0.7rem",
              borderRadius: "9999px",
              cursor: "default",
            }}
          >
            {q}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const submit = async () => {
    const question = input.trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    textareaRef.current?.focus();

    try {
      const data = await sendQuery(question, conversationId);
      setConversationId(data.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.answer,
          sources: data.sources,
          confidence: data.confidence,
          context_used: data.context_used,
          route_category: data.route_category,
          route_confidence: data.route_confidence,
          disclaimer: data.disclaimer,
          isError: false,
        },
      ]);
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        "Unable to reach the server. Make sure the backend is running on port 8000.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: detail, isError: true },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const disabled = loading || !input.trim();

  return (
    <div style={S.container}>
      <div style={S.feed}>
        {messages.length === 0 && <WelcomeScreen />}

        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} style={S.userRow}>
              <div style={S.roleLabel}>You</div>
              <div style={S.userBubble}>{msg.text}</div>
            </div>
          ) : (
            <AssistantMessage key={i} msg={msg} />
          )
        )}

        {loading && (
          <div style={{ alignSelf: "flex-start", maxWidth: "82%" }}>
            <div style={S.roleLabel}>Clinical AI</div>
            <div style={S.loadingCard}>
              <span>Searching knowledge base</span>
              <span style={{ animation: "none", opacity: 0.5 }}>&#8230;</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <p style={S.footerNote}>
        For licensed clinical professionals only &middot; Not a substitute for independent clinical judgment
      </p>

      <div style={S.inputArea}>
        <textarea
          ref={textareaRef}
          style={S.textarea}
          rows={2}
          placeholder="Ask a clinical question... (Enter to send, Shift+Enter for new line)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={loading}
        />
        <button
          style={S.sendBtn(disabled)}
          onClick={submit}
          disabled={disabled}
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}