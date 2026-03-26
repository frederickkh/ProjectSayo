"use client";

import { useState, useEffect, useRef } from "react";
import { Sun, Moon, History, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { sendMessage } from "@/app/actions/chat";

type Message = {
  id: number;
  text: string;
  sender: "user" | "bot";
  timestamp: Date;
};

type Conversation = {
  id: number;
  title: string;
  messages: Message[];
};

const WELCOME_PROMPTS = [
  "How do I access my student dashboard?",
  "How do I create a class in Sayo Academy?",
  "How do I use the AI grading feature?",
  "How do I invite students to my class?",
];

export default function ChatSkeleton() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  // Save current messages as a conversation when starting a new one
  const saveCurrentConversation = () => {
    if (messages.length === 0) return;
    const title = messages[0].text.slice(0, 40) + (messages[0].text.length > 40 ? "..." : "");
    const newConversation: Conversation = {
      id: Date.now(),
      title,
      messages,
    };
    setConversations((prev) => [newConversation, ...prev]);
  };

  const handleNewChat = () => {
    saveCurrentConversation();
    setMessages([]);
    setActiveConversationId(null);
    setSidebarOpen(false);
  };

  const handleLoadConversation = (conversation: Conversation) => {
    saveCurrentConversation();
    setMessages(conversation.messages);
    setActiveConversationId(conversation.id);
    setSidebarOpen(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now(),
      text: input,
      sender: "user",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const botResponse = await sendMessage(input);
      const botMessage: Message = {
        id: Date.now() + 1,
        text: botResponse,
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: Date.now() + 1,
        text: "Sorry, I couldn't generate a response. Please try again.",
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handlePromptClick = (prompt: string) => {
    setInput(prompt);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const formatTime = (date: Date) =>
    date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="relative w-full flex h-[650px] rounded-2xl overflow-hidden shadow-lg border border-slate-200 dark:border-slate-700">

      {/* Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="absolute inset-0 bg-black/30 z-10"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Slide-in Sidebar */}
      <div
        className={`absolute top-0 left-0 h-full w-64 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 z-20 transform transition-transform duration-300 flex flex-col ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Sidebar Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <span className="font-semibold text-slate-800 dark:text-white text-sm">Chat History</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-white transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-3 border-b border-slate-200 dark:border-slate-700">
          <button
            onClick={handleNewChat}
            className="w-full py-2 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition"
          >
            + New Chat
          </button>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-slate-500 text-center mt-6 px-4">
              No history yet. Start a conversation!
            </p>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => handleLoadConversation(conv)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition truncate ${
                  activeConversationId === conv.id
                    ? "bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium"
                    : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                }`}
              >
                {conv.title}
              </button>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex flex-col flex-1 bg-gradient-to-b from-white to-slate-50 dark:from-slate-800 dark:to-slate-900">

        {/* Top Bar */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition"
            aria-label="Open history"
          >
            <History className="w-5 h-5" />
          </button>
          <span className="text-sm font-semibold text-slate-700 dark:text-white">Sayo Assistant</span>
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition"
            aria-label="Toggle dark mode"
          >
            {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>

        {/* Messages Container */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center space-y-6">
              <div className="text-center space-y-2 mb-4">
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white">
                  How can I assist you?
                </h3>
                <p className="text-slate-600 dark:text-slate-400">
                  Get help accessing and managing Sayo Academy
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-md">
                {WELCOME_PROMPTS.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => handlePromptClick(prompt)}
                    className="p-3 text-left rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 hover:border-blue-400 dark:hover:border-blue-400 hover:shadow-md transition text-sm text-slate-700 dark:text-slate-200 font-medium group"
                  >
                    <span className="group-hover:text-blue-600 dark:group-hover:text-blue-400 transition">{prompt}</span>
                  </button>
                ))}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 pt-4">
                Powered by sayo.ai • Fast and accurate responses
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 group ${msg.sender === "user" ? "justify-end" : "justify-start"} animate-in fade-in slide-in-from-bottom-2 duration-300`}
                >
                  {msg.sender === "bot" && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center flex-shrink-0 mt-1">
                      <span className="text-white text-sm font-bold">S</span>
                    </div>
                  )}

                  <div className={`flex flex-col max-w-xs lg:max-w-md ${msg.sender === "user" ? "items-end" : "items-start"}`}>
                    <div
                      className={`inline-block px-4 py-3 rounded-lg break-words ${
                        msg.sender === "user"
                          ? "bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-md"
                          : "bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-600"
                      }`}
                    >
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                    </div>
                    {/* Timestamp on hover */}
                    <span className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                      {formatTime(msg.timestamp)}
                    </span>
                  </div>

                  {msg.sender === "user" && (
                    <div className="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-600 flex items-center justify-center flex-shrink-0 mt-1">
                      <span className="text-slate-700 dark:text-slate-300 text-sm font-bold">U</span>
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex gap-3 justify-start animate-in fade-in">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center flex-shrink-0">
                    <span className="text-white text-sm font-bold">S</span>
                  </div>
                  <div className="flex items-center gap-1 px-4 py-3 bg-slate-100 dark:bg-slate-700 rounded-lg">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce" style={{ animationDelay: "0ms" }}></div>
                      <div className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce" style={{ animationDelay: "150ms" }}></div>
                      <div className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce" style={{ animationDelay: "300ms" }}></div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input Section */}
        <div className="border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              className="flex-1 rounded-full border-slate-300 dark:border-slate-600 dark:bg-slate-700 dark:text-white dark:placeholder-slate-400 bg-slate-50 h-10"
              placeholder="Ask me anything..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-5 h-10 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-full font-semibold hover:from-blue-700 hover:to-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-md hover:shadow-lg flex items-center gap-2"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              ) : (
                <>
                  Send
                  <svg className="w-4 h-4 rotate-45 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}