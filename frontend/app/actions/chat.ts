"use server";

import OpenAI from "openai";

const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
});

export async function sendMessage(message: string) {
    const response = await openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
            {
                role: "system", content: "You are a helpful assistant."},
            {
                role: "user", content: message
            },
            ],
        });
    return response.choices[0]?.message?.content ?? "Sorry, I couldn't generate a response.";
}
console.log("KEY:", process.env.OPENAI_API_KEY);