import axios from "axios";

const client = axios.create({ baseURL: "/api" });

/**
 * Send a clinical query to the backend.
 * @param {string} question
 * @param {string|null} conversationId
 * @returns {Promise<QueryResponse>}
 */
export async function sendQuery(question, conversationId = null) {
  const { data } = await client.post("/query", {
    question,
    conversation_id: conversationId,
  });
  return data;
}

/**
 * Check backend health.
 * @returns {Promise<{status: string}>}
 */
export async function checkHealth() {
  const { data } = await client.get("/health");
  return data;
}