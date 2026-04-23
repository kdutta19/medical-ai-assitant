import React, { useState, useRef, useEffect } from "react";
import axios from "axios";

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    maxWidth: "900px",
    margin: "0 auto",
    padding: "1rem",
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
    padding: "1rem 0",
  },
  bubble: (role) => ({
    maxWidth: "75%",
    padding: "0.75rem 1rem",
    borderRadius: "1rem",
    lineHeight: "1.6",
    whiteSpace: "pre-wrap",
    alignSelf: role === "user" ? "flex-end" : "flex-start",
    backgroundColor: role === "user" ? "#3182ce" : "#ffffff",
    color: role === "user" ? "#ffffff" : "#1a202c",
    boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
  }),
  roleLabel: {
    fontSize: "0.7rem",
    fontWeight: "600",
    marginBottom: "0.25rem",
    opacity: 0.6,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  inputArea: {
    display: "flex",
    gap: "0.5rem",
    padding: "0.75rem 0",
    borderTop: "1px solid #e2e8f0",
  },
  textarea: {
    flex: 1,
    padding: "0.75rem",
    borderRadius: "0.5rem",
    border: "1px solid #cbd5e0",
    resize: "none",
    fontSize: "0.95rem",
    fontFamily: "inherit",
    outline: "none",
  },
  button: (disabled) => ({
    padding: "0.75rem 1.5rem",
    borderRadius: "0.5rem",
    border: "none",
    backgroundColor: disabled ? "#a0aec0" : "#3182ce",
    color: "#fff",
    cursor: disabled ? "not-allowed" : "pointer",
    fontWeight: "600",
    fontSize: "0.95rem",
    transition: "background-color 0.2s",
  }),
  disclaimer: {
    fontSize: "0.75rem",
    color: "#718096",
    textAlign: "center",
    padding: "0.25rem 0 0.5rem",
  },
};

export default function ChatInterface() {
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, loading]);

  const sendMessage = async () => {
    const message = input.trim();
    if (!message || loading) return;

    const userMsg = { role: "user", content: message };
    setHistory((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await axios.post("/api/chat", {
        message,
        conversation_id: conversationId,
        history: history,
      });
      setConversationId(res.data.conversation_id);
      setHistory((prev) => [
        ...prev,
        { role: "assistant", content: res.data.response },
      ]);
    } catch {
      setHistory((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "An error occurred. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.messages}>
        {history.length === 0 && (
          <div style={{ textAlign: "center", color: "#718096", marginTop: "3rem" }}>
            <p style={{ fontSize: "1.2rem", fontWeight: "600" }}>Clinical AI Assistant</p>
            <p style={{ fontSize: "0.9rem", marginTop: "0.5rem" }}>
              Ask about clinical guidelines, drug references, differential diagnosis support, and more.
            </p>
          </div>
        )}
        {history.map((msg, i) => (
          <div
            key={i}
            style={{ alignSelf: msg.role === "user" ? "flex-end" : "flex-start", maxWidth: "75%" }}
          >
            <div style={styles.roleLabel}>{msg.role === "user" ? "You" : "Assistant"}</div>
            <div style={styles.bubble(msg.role)}>{msg.content}</div>
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: "flex-start" }}>
            <div style={styles.roleLabel}>Assistant</div>
            <div style={styles.bubble("assistant")}>Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <p style={styles.disclaimer}>
        For clinical decision support only. Always consult a licensed physician for diagnosis and treatment.
      </p>

      <div style={styles.inputArea}>
        <textarea
          style={styles.textarea}
          rows={2}
          placeholder="Ask a clinical question... (Shift+Enter for new line)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          style={styles.button(loading || !input.trim())}
          onClick={sendMessage}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
