import React from "react";
import ChatInterface from "./components/ChatInterface";

export default function App() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header
        style={{
          backgroundColor: "#1a365d",
          color: "#ffffff",
          padding: "0.65rem 1.5rem",
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          flexShrink: 0,
          boxShadow: "0 1px 4px rgba(0,0,0,0.2)",
        }}
      >
        <span style={{ fontSize: "1.1rem", fontWeight: "700", letterSpacing: "0.02em" }}>
          Clinical AI Assistant
        </span>
        <span
          style={{
            fontSize: "0.65rem",
            fontWeight: "700",
            backgroundColor: "#2b6cb0",
            padding: "0.18rem 0.5rem",
            borderRadius: "0.25rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          BETA
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: "0.72rem",
            color: "#90cdf4",
            letterSpacing: "0.03em",
          }}
        >
          RAG &middot; Grounded &middot; Claude-powered
        </span>
      </header>

      <main style={{ flex: 1, overflow: "hidden" }}>
        <ChatInterface />
      </main>
    </div>
  );
}