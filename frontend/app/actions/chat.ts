"use server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ChatResponse {
    response: string;
    sources: Array<{
        title: string;
        type: string;
        similarity: number;
    }>;
}

export async function sendMessage(message: string, manualType?: string): Promise<string> {
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: message,
                manual_type: manualType || null
            }),
        });

        if (!response.ok) {
            console.error("Chat API error:", response.status, response.statusText);
            return "Sorry, I couldn't generate a response. Please try again.";
        }

        const data: ChatResponse = await response.json();
        return data.response;
    } catch (error) {
        console.error("Chat error:", error);
        return "Sorry, I encountered an error. Please check that the backend server is running.";
    }
}

export async function sendMessageWithSources(
    message: string,
    manualType?: string
): Promise<ChatResponse> {
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: message,
                manual_type: manualType || null
            }),
        });

        if (!response.ok) {
            console.error("Chat API error:", response.status, response.statusText);
            return {
                response: "Sorry, I couldn't generate a response. Please try again.",
                sources: []
            };
        }

        return await response.json();
    } catch (error) {
        console.error("Chat error:", error);
        return {
            response: "Sorry, I encountered an error. Please check that the backend server is running.",
            sources: []
        };
    }
}