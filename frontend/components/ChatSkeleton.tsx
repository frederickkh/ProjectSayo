"use client";

import { useState, useEffect, useRef } from "react";
import { Sun, Moon, History, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { sendMessage } from "@/app/actions/chat";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

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
            // Welcome State
            <div className="h-full flex flex-col items-center justify-center px-4">
              <div className="text-center mb-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-blue-700 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-xl rotate-3 hover:rotate-0 transition-transform duration-500">
                  <span className="text-white text-3xl font-black">S</span>
                </div>
                <h3 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-3">
                  Welcome to Sayo
                </h3>
                <p className="text-slate-500 dark:text-slate-400 text-base max-w-sm mx-auto leading-relaxed">
                  Your intelligent companion for mastering Sayo Academy. How can I help you today?
                </p>
              </div>

              {/* Suggested Prompts */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl animate-in fade-in slide-in-from-bottom-8 duration-1000 delay-200">
                {WELCOME_PROMPTS.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => handlePromptClick(prompt)}
                    className="p-4 text-left rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-lg transition-all duration-300 group relative overflow-hidden"
                  >
                    <div className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <svg
                        className="w-4 h-4 text-blue-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M14 5l7 7m0 0l-7 7m7-7H3"
                        />
                      </svg>
                    </div>
                    <span className="text-sm text-slate-700 dark:text-slate-200 font-semibold leading-snug group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors block pr-6">
                      {prompt}
                    </span>
                  </button>
                ))}
              </div>

              <div className="text-[11px] font-bold text-blue-600/50 dark:text-blue-400/30 uppercase tracking-[0.2em] mt-12 animate-in fade-in duration-1000 delay-500">
                Powered by Sayo.ai
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
                      className={`inline-block px-4 py-3 rounded-2xl break-words shadow-sm transition-all duration-300 ${
                        msg.sender === "user"
                          ? "bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-tr-none"
                          : "bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-700 rounded-tl-none"
                      }`}
                    >
                      {msg.sender === "bot" ? (
                        <div className="text-sm leading-relaxed max-w-full overflow-hidden">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              code({node, inline, className, children, ...props}: any) {
                                const match = /language-(\w+)/.exec(className || "");
                                return !inline && match ? (
                                  <div className="relative group my-4">
                                    <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                      <button
                                        onClick={() =>
                                          navigator.clipboard.writeText(String(children))
                                        }
                                        className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 text-[10px] font-medium transition"
                                      >
                                        Copy
                                      </button>
                                    </div>
                                    <SyntaxHighlighter
                                      style={vscDarkPlus}
                                      language={match[1]}
                                      PreTag="div"
                                      className="rounded-xl !bg-slate-900 !m-0 p-4 text-xs border border-slate-800"
                                      {...props}
                                    >
                                      {String(children).replace(/\n$/, "")}
                                    </SyntaxHighlighter>
                                  </div>
                                ) : (
                                  <code
                                    className={`${className} bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-[0.9em] font-mono font-semibold text-blue-600 dark:text-blue-400`}
                                    {...props}
                                  >
                                    {children}
                                  </code>
                                );
                              },
                              a: ({node, ...props}) => (
                                <a
                                  {...props}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 dark:text-blue-400 underline hover:no-underline font-semibold"
                                />
                              ),
                              ul: ({node, ...props}) => (
                                <ul {...props} className="list-disc pl-5 my-3 space-y-2" />
                              ),
                              ol: ({node, ...props}) => (
                                <ol {...props} className="list-decimal pl-5 my-3 space-y-2" />
                              ),
                              p: ({node, ...props}) => <p {...props} className="mb-3 last:mb-0" />,
                              h1: ({node, ...props}) => (
                                <h1
                                  {...props}
                                  className="text-xl font-bold mt-6 mb-3 text-slate-900 dark:text-white"
                                />
                              ),
                              h2: ({node, ...props}) => (
                                <h2
                                  {...props}
                                  className="text-lg font-bold mt-5 mb-2 text-slate-900 dark:text-white"
                                />
                              ),
                              h3: ({node, ...props}) => (
                                <h3
                                  {...props}
                                  className="text-base font-bold mt-4 mb-2 text-slate-900 dark:text-white"
                                />
                              ),
                              blockquote: ({node, ...props}) => (
                                <blockquote
                                  {...props}
                                  className="border-l-4 border-blue-500 pl-4 italic my-4 text-slate-600 dark:text-slate-400 py-1"
                                />
                              ),
                              hr: ({node, ...props}) => (
                                <hr {...props} className="my-6 border-slate-200 dark:border-slate-700" />
                              ),
                              table: ({node, ...props}) => (
                                <div className="overflow-x-auto my-4">
                                  <table
                                    {...props}
                                    className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden"
                                  />
                                </div>
                              ),
                              th: ({node, ...props}) => (
                                <th
                                  {...props}
                                  className="px-3 py-2 bg-slate-50 dark:bg-slate-900 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider"
                                />
                              ),
                              td: ({node, ...props}) => (
                                <td
                                  {...props}
                                  className="px-3 py-2 text-xs border-t border-slate-200 dark:border-slate-700"
                                />
                              ),
                            }}
                          >
                            {msg.text}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">
                          {msg.text}
                        </p>
                      )}
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
        <div className="border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 backdrop-blur-md p-6">
          <form onSubmit={handleSubmit} className="relative group max-w-3xl mx-auto w-full">
            <Input
              className="w-full pl-6 pr-14 py-6 rounded-2xl border-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder-slate-500 bg-slate-50 border-2 focus-visible:ring-blue-500 focus-visible:border-blue-500 transition-all shadow-sm group-hover:shadow-md h-14 text-base"
              placeholder="How can Sayo help you today?"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="absolute right-2 top-2 p-2.5 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-30 disabled:hover:bg-blue-600 transition-all shadow-md active:scale-95 h-10 w-10 flex items-center justify-center z-10"
              title="Send Message"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              )}
            </button>
          </form>
          <div className="text-[10px] text-center text-slate-400 mt-3 font-medium tracking-tight">
            Sayo AI can make mistakes. Check important info.
          </div>
        </div>
      </div>
    </div>
  );
}