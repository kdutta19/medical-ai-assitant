import React from "react";
import ChatInterface from "./components/ChatInterface";

export default function App() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header
        style={{
          backgroundColor: "#1a365d",
          color: "#ffffff",
          padding: "0.75rem 1.5rem",
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: "1.4rem" }}>Clinical AI Assistant</span>
        <span
          style={{
            fontSize: "0.7rem",
            backgroundColor: "#2b6cb0",
            padding: "0.2rem 0.5rem",
            borderRadius: "0.25rem",
            letterSpacing: "0.05em",
          }}
        >
          BETA
        </span>
      </header>
      <main style={{ flex: 1, overflow: "hidden" }}>
        <ChatInterface />
      </main>
    </div>
  );
}
