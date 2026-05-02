/**
 * Chat service - handles API communication for chat messages and history
 */

import { getOrCreateDeviceId } from "./deviceId";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ChatMessage {
  id: string;
  user_message: string;
  bot_response: string;
  sources?: Array<{
    title: string;
    url: string;
    type: string;
    page?: number;
    similarity: number;
  }>;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  sources: Array<{
    title: string;
    url: string;
    type: string;
    page?: number;
    similarity: number;
  }>;
}

/**
 * Send a message and get a chat response
 */
export async function sendChatMessage(
  message: string,
  sessionId?: string | null,
  manualType?: string
): Promise<ChatResponse> {
  const deviceId = getOrCreateDeviceId();

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        device_id: deviceId,
        manual_type: manualType,
      }),
    });

    if (!response.ok) {
      console.error("Chat API error:", response.status, response.statusText);
      throw new Error(`Chat API error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Failed to send chat message:", error);
    throw error;
  }
}

/**
 * Get all chat sessions for the current device
 */
export async function getChatSessions(limit: number = 20): Promise<ChatSession[]> {
  const deviceId = getOrCreateDeviceId();

  try {
    const response = await fetch(`${API_BASE_URL}/chat/sessions/${deviceId}?limit=${limit}`);

    if (!response.ok) {
      console.error("Failed to get chat sessions:", response.status);
      return [];
    }

    const data = await response.json();
    return data.sessions || [];
  } catch (error) {
    console.error("Failed to fetch chat sessions:", error);
    return [];
  }
}

/**
 * Get all messages in a specific chat session
 */
export async function getChatHistory(sessionId: string): Promise<ChatMessage[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/chat/history/${sessionId}`);

    if (!response.ok) {
      console.error("Failed to get chat history:", response.status);
      return [];
    }

    const data = await response.json();
    return data.messages || [];
  } catch (error) {
    console.error("Failed to fetch chat history:", error);
    return [];
  }
}

/**
 * Create a new chat session
 */
export async function createNewSession(title?: string): Promise<string> {
  const deviceId = getOrCreateDeviceId();

  try {
    const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        device_id: deviceId,
        title: title || "New Chat",
      }),
    });

    if (!response.ok) {
      console.error("Failed to create session:", response.status);
      throw new Error("Failed to create session");
    }

    const data = await response.json();
    return data.session_id;
  } catch (error) {
    console.error("Failed to create new session:", error);
    throw error;
  }
}

/**
 * Get the current device ID
 */
export function getCurrentDeviceId(): string {
  return getOrCreateDeviceId();
}
