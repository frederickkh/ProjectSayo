"use server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ChatResponse {
    response: string;
    session_id: string;
    sources: Array<{
        title: string;
        type: string;
        similarity: number;
    }>;
}

export async function sendMessage(message: string, manualType?: string, sessionId?: string | null): Promise<{ text: string; sessionId: string }> {
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: message,
                manual_type: manualType || null,
                session_id: sessionId || null
            }),
        });

        if (!response.ok) {
            console.error("Chat API error:", response.status, response.statusText);
            return { text: "Sorry, I couldn't generate a response. Please try again.", sessionId: sessionId || "" };
        }

        const data: ChatResponse = await response.json();
        return { text: data.response, sessionId: data.session_id };
    } catch (error) {
        console.error("Chat error:", error);
        return { text: "Sorry, I encountered an error. Please check that the backend server is running.", sessionId: sessionId || "" };
    }
}

export async function sendMessageWithSources(
    message: string,
    manualType?: string,
    sessionId?: string | null
): Promise<ChatResponse> {
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: message,
                manual_type: manualType || null,
                session_id: sessionId || null
            }),
        });

        if (!response.ok) {
            console.error("Chat API error:", response.status, response.statusText);
            return {
                response: "Sorry, I couldn't generate a response. Please try again.",
                sources: [],
                session_id: sessionId || ""
            };
        }

        return await response.json();
    } catch (error) {
        console.error("Chat error:", error);
        return {
            response: "Sorry, I encountered an error. Please check that the backend server is running.",
            sources: [],
            session_id: sessionId || ""
        };
    }
}