"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import { Copy, Check } from "lucide-react";

interface MarkdownBubbleMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export default function MarkdownBubble({
  msg,
  isUser,
  copiedId,
  onCopy,
}: {
  msg: MarkdownBubbleMessage;
  isUser: boolean;
  copiedId: string | null;
  onCopy: (id: string, text: string) => void;
}) {
  return (
    <div
      className={`group relative max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
        isUser
          ? "bg-blue-600 text-white rounded-br-none"
          : "bg-slate-900 border border-slate-800 text-slate-200 rounded-bl-none"
      }`}
    >
      {!isUser ? (
        <div className="prose prose-invert prose-sm max-w-none prose-pre:bg-slate-950 prose-pre:border prose-pre:border-slate-800">
          <ReactMarkdown>{msg.content}</ReactMarkdown>
        </div>
      ) : (
        <p className="whitespace-pre-wrap">{msg.content}</p>
      )}

      <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-slate-400">
        <span>{msg.timestamp}</span>
        {!isUser && msg.content && (
          <button
            onClick={() => onCopy(msg.id, msg.content)}
            className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 hover:text-slate-200"
          >
            {copiedId === msg.id ? (
              <Check className="w-3 h-3 text-emerald-400" />
            ) : (
              <Copy className="w-3 h-3" />
            )}
            <span>{copiedId === msg.id ? "Copied" : "Copy"}</span>
          </button>
        )}
      </div>
    </div>
  );
}
