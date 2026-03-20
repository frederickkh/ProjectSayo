"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { sendMessage } from "@/app/actions/chat";

type Message = {
  id: number;
  text: string;
  sender: "user" | "bot";
};

export default function ChatSkeleton() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Open AI integration
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = { id: Date.now(), text: input, sender: "user" };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const botResponse = await sendMessage(input);
      const botMessage: Message = {
        id: Date.now() + 1, 
        text: botResponse,
        sender: "bot",
      };
      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: Date.now() + 1,
        text: "Sorry, I couldn't generate a response.",
        sender: "bot",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };
  
  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);
    
  return (
    <div className="w-full p-4 flex flex-col h-[600px] border border-border rounded-lg bg-card">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto mb-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${
              msg.sender === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {/*Removed the ml-auto/mr-auto from here and added w-fit, didnt get fixed */}
            <div className={`w-fit max-w-[70%] ${msg.sender === "user" ? "ml-auto" : "mr-auto"}`}>
              <Card
                className={`px-3 py-2 ${
                  msg.sender === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {msg.text}
              </Card>
            </div>
          </div>
        ))}
        
        {/* Loading indicator and scroll ref*/}
        {loading && (
          <div className="flex justify-start">
            <Card className="px-3 py-2 bg-muted text-muted-foreground animate-pulse max-w-[50%]">
              Typing...
            </Card>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          className="flex-1"
          placeholder="Type a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <Button type="submit" disabled={loading}>Send</Button>
      </form>
    </div>
  );
}