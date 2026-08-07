"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Sparkles,
  RefreshCw,
  Bot,
  User,
  Wrench,
  LineChart,
} from "lucide-react";
import MarkdownBubble from "./components/MarkdownBubble";
import InsightCard, { Insight } from "./components/InsightCard";
import InsightCardSkeleton from "./components/InsightCardSkeleton";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  insight?: Insight;
  timestamp: string;
}

const NON_ANALYTICAL_SPEC_IDS = new Set(["conversational", "abusive_deescalation", "out_of_scope", "none"]);

function mapInsightResponse(json: any): Insight {
  return {
    question: json.question ?? "",
    executiveSummary: json.executive_summary ?? "",
    confidence: json.confidence ?? { score: 0, rationale: "" },
    knownIssueMatch: json.known_issue_match ?? false,
    matchedKnownIssue: json.matched_known_issue ?? "",
    cuts: json.cuts ?? {},
    views: json.views ?? { metric_deltas: [] },
    sqlQueries: json.sql_queries ?? [],
    specId: json.spec_id ?? "",
    traceId: json.trace_id ?? "",
    traceUrl: json.trace_url ?? "",
  };
}

const AGENT_MODELS = [
  {
    id: "atlys-instrumentation",
    name: "Atlys Instrumentation Engineer",
    cuj: "CUJ 1: Schema Ingestion & DDL",
    desc: "Infers ClickHouse schemas from specs, generates DDL, Materialized Views, and Context Diffs.",
    icon: Wrench,
    badgeColor: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  },
  {
    id: "atlys-analyst",
    name: "Atlys Product Analyst",
    cuj: "CUJ 2: ClickHouse Analytics",
    desc: "Answers natural language business questions, queries ClickHouse Cloud, and analyzes conversion funnels.",
    icon: LineChart,
    badgeColor: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  },
];

const SUGGESTIONS = [
  { text: "ingest 01_express_checkout", model: "atlys-instrumentation" },
  { text: "Show available specs and schema status", model: "atlys-instrumentation" },
  { text: "What is the checkout to payment completion conversion rate?", model: "atlys-analyst" },
  { text: "Show hourly payment drop-off by provider", model: "atlys-analyst" },
];

export default function ChatPage() {
  const [selectedModel, setSelectedModel] = useState("atlys-instrumentation");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "👋 **Welcome to InsightMesh!**\n\nI am your autonomous **ClickHouse & Event Analytics Intelligence Engine**.\n\n* Select **Atlys Instrumentation Engineer** to infer schemas, generate ClickHouse DDL, and inspect context diffs.\n* Select **Atlys Product Analyst** to run natural language SQL analytics and conversion funnel queries.\n\nHow can I help you today?",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleSend = async (textToSend?: string) => {
    const query = textToSend || input.trim();
    if (!query || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput("");
    setIsLoading(true);

    const assistantMsgId = `assistant-${Date.now()}`;
    const placeholderAssistant: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages([...newMessages, placeholderAssistant]);

    if (selectedModel === "atlys-analyst") {
      try {
        const res = await fetch("/api/analyze/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: query, spec_id: "chat" }),
        });

        if (!res.ok) {
          throw new Error(`Server returned ${res.status}`);
        }

        const json = await res.json();
        const insight = mapInsightResponse(json);

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, content: json.answer_md || insight.executiveSummary, insight }
              : msg
          )
        );
      } catch (err: any) {
        console.error("Error fetching analyst insight:", err);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  content: `⚠️ **Error connecting to InsightMesh backend:** ${err.message}\n\nPlease check that the backend service is reachable.`,
                }
              : msg
          )
        );
      } finally {
        setIsLoading(false);
      }
      return;
    }

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: selectedModel,
          messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      if (!res.body) {
        throw new Error("No response body received");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[DONE]") continue;
            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta?.content || "";
              accumulated += delta;
            } catch {
              accumulated += data;
            }
          } else if (line.trim().length > 0 && !line.startsWith(":")) {
            accumulated += line;
          }
        }

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId ? { ...msg, content: accumulated } : msg
          )
        );
      }
    } catch (err: any) {
      console.error("Error streaming chat:", err);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content:
                  msg.content ||
                  `⚠️ **Error connecting to InsightMesh backend:** ${err.message}\n\nPlease check that the backend service is reachable.`,
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const activeAgent = AGENT_MODELS.find((m) => m.id === selectedModel)!;
  const ActiveIcon = activeAgent.icon;

  return (
    <div className="flex flex-col h-screen max-w-5xl mx-auto w-full px-4 sm:px-6">
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between py-4 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 shadow-lg shadow-blue-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              InsightMesh
            </h1>
            <p className="text-xs text-slate-400">Atlys Event Analytics & Schema Engine</p>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:flex-initial">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full sm:w-64 bg-slate-900 border border-slate-700 hover:border-slate-600 rounded-lg px-3 py-2 text-xs font-medium text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
            >
              {AGENT_MODELS.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>ClickHouse Online</span>
          </div>
        </div>
      </header>

      <div className="py-2.5 px-3.5 my-3 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-center justify-between text-xs text-slate-300">
        <div className="flex items-center gap-2">
          <ActiveIcon className="w-4 h-4 text-blue-400" />
          <span className="font-semibold text-slate-200">{activeAgent.name}</span>
          <span className="hidden md:inline text-slate-500">•</span>
          <span className="hidden md:inline text-slate-400">{activeAgent.desc}</span>
        </div>
        <span className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold ${activeAgent.badgeColor}`}>
          {activeAgent.cuj}
        </span>
      </div>

      <main className="flex-1 overflow-y-auto space-y-4 py-2 pr-1">
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          const showInsightCard =
            !isUser && msg.insight && !NON_ANALYTICAL_SPEC_IDS.has(msg.insight.specId);
          return (
            <div
              key={msg.id}
              className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
            >
              {!isUser && (
                <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot className="w-4 h-4 text-blue-400" />
                </div>
              )}

              {showInsightCard ? (
                <div className="max-w-[85%] w-full">
                  <InsightCard insight={msg.insight!} />
                  <div className="mt-1 text-[10px] text-slate-500">{msg.timestamp}</div>
                </div>
              ) : (
                <MarkdownBubble msg={msg} isUser={isUser} copiedId={copiedId} onCopy={handleCopy} />
              )}

              {isUser && (
                <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User className="w-4 h-4 text-slate-300" />
                </div>
              )}
            </div>
          );
        })}

        {isLoading &&
          (selectedModel === "atlys-analyst" ? (
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
              </div>
              <div className="max-w-[85%] w-full">
                <InsightCardSkeleton />
              </div>
            </div>
          ) : (
            <div className="flex gap-3 items-center text-xs text-slate-400 py-2">
              <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
                <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
              </div>
              <span>Agent is consulting ClickHouse & Gemini 3...</span>
            </div>
          ))}

        <div ref={messagesEndRef} />
      </main>

      {messages.length <= 2 && (
        <div className="py-2">
          <p className="text-[11px] text-slate-400 font-medium mb-1.5">Suggested Prompts:</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {SUGGESTIONS.map((s, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setSelectedModel(s.model);
                  handleSend(s.text);
                }}
                className="text-left px-3 py-2 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800/80 hover:border-slate-700 text-xs text-slate-300 transition-all flex items-center justify-between"
              >
                <span className="truncate">{s.text}</span>
                <span className="text-[10px] text-slate-500 ml-2 whitespace-nowrap">
                  {s.model === "atlys-instrumentation" ? "CUJ 1" : "CUJ 2"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <footer className="py-3 border-t border-slate-800">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="relative flex items-center"
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${activeAgent.name} (Press Enter to send)...`}
            className="w-full bg-slate-900 border border-slate-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 resize-none pr-12 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
        <p className="text-[10px] text-center text-slate-500 mt-2">
          InsightMesh • Powered by ClickHouse Cloud, chDB, Gemini 3 Flash & CrewAI
        </p>
      </footer>
    </div>
  );
}
