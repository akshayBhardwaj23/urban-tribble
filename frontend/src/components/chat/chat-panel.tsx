"use client";

import { useRef, useState, useEffect, useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";

const ALL_DATASETS_VALUE = "__all__";

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
}

interface Dataset {
  id: string;
  name: string;
  row_count?: number | null;
  column_count?: number | null;
}

interface ChatPanelProps {
  datasets: Dataset[];
}

export function ChatOverlay({ datasets }: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [selectedDataset, setSelectedDataset] =
    useState<string>(ALL_DATASETS_VALUE);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const isAllDatasets = selectedDataset === ALL_DATASETS_VALUE;

  const anchorId = useMemo(
    () => (isAllDatasets ? datasets[0]?.id : selectedDataset),
    [isAllDatasets, datasets, selectedDataset]
  );

  const { data: historyData } = useQuery({
    queryKey: ["chat-history", anchorId, isAllDatasets ? "workspace" : "dataset"],
    queryFn: () =>
      api.getChatHistory(anchorId!, {
        workspace: isAllDatasets,
      }),
    enabled: open && !!anchorId,
  });

  useEffect(() => {
    if (!open || !anchorId) return;
    if (historyData === undefined) {
      setMessages([]);
      return;
    }
    setMessages(
      historyData.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
      }))
    );
  }, [open, anchorId, isAllDatasets, historyData]);

  const chatMutation = useMutation({
    mutationFn: (question: string) =>
      isAllDatasets
        ? api.chatWorkspace(question)
        : api.chat(selectedDataset, question),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer },
      ]);
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err.message}` },
      ]);
    },
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, chatMutation.isPending]);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  const handleSend = () => {
    if (!input.trim()) return;
    if (!isAllDatasets && !selectedDataset) return;
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    chatMutation.mutate(input);
    setInput("");
  };

  const handleDatasetChange = (id: string) => {
    setSelectedDataset(id);
    setMessages([]);
  };

  const showEmptySuggestions =
    messages.length === 0 && !chatMutation.isPending;

  const sendSuggestion = (text: string) => {
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    chatMutation.mutate(text);
  };

  if (!datasets.length) return null;

  const totalRows = datasets.reduce(
    (sum, ds) => sum + (ds.row_count ?? 0),
    0
  );
  const selectedName = isAllDatasets
    ? "all sources in this workspace"
    : datasets.find((d) => d.id === selectedDataset)?.name;

  const suggestions = isAllDatasets
    ? [
        "Summarize how my sources look together",
        "What is total revenue across all sources?",
        "Compare sales and expenses",
      ]
    : [
        "What was total revenue?",
        "Which category had the highest sales?",
        "Show the monthly trend",
      ];

  return (
    <>
      {/* Floating trigger — pill with label when closed; compact close when open */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={
          open
            ? "fixed bottom-5 right-5 z-50 flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 active:scale-95"
            : "fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full bg-primary pl-3 pr-4 py-2.5 text-primary-foreground shadow-lg transition-transform hover:scale-[1.02] active:scale-95"
        }
        aria-label={open ? "Close Q&A" : `Ask ${PRODUCT_NAME}`}
      >
        {open ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-sm font-semibold tracking-tight whitespace-nowrap">
              Ask {PRODUCT_NAME}
            </span>
          </>
        )}
      </button>

      {/* Chat panel — anchored to bottom-right, capped to viewport */}
      {open && (
        <div
          className="fixed z-50 flex flex-col rounded-xl border bg-card shadow-2xl animate-in slide-in-from-bottom-4 fade-in duration-200"
          style={{
            bottom: "4.5rem",
            right: "1.25rem",
            width: "min(400px, calc(100vw - 2rem))",
            maxHeight: "calc(100vh - 6rem)",
          }}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2 border-b px-4 py-2.5 shrink-0">
            <div className="flex flex-col gap-0.5 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary shrink-0">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <span className="text-sm font-semibold">Q&A on your data</span>
                {isAllDatasets && (
                  <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded-full font-medium">
                    Workspace
                  </span>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground pl-6 leading-tight">
                Grounded answers from your imported sources
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors shrink-0"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Dataset selector */}
          <div className="border-b px-3 py-2 shrink-0">
            <select
              className="w-full rounded-md border px-2 py-1.5 text-xs bg-background"
              value={selectedDataset}
              onChange={(e) => handleDatasetChange(e.target.value)}
            >
              <option value={ALL_DATASETS_VALUE}>
                All sources ({datasets.length} files,{" "}
                {totalRows.toLocaleString()} rows)
              </option>
              {datasets.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                  {ds.row_count
                    ? ` (${ds.row_count.toLocaleString()} rows)`
                    : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Messages — this is the only scrollable/flexible section */}
          <div
            ref={scrollRef}
            className="flex-1 min-h-0 overflow-y-auto px-4 py-3"
          >
            {showEmptySuggestions ? (
              <div className="flex items-center justify-center text-center py-8">
                <div className="space-y-2 max-w-[280px]">
                  <p className="text-sm font-medium text-foreground">
                    Ask about {selectedName}
                  </p>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    {isAllDatasets
                      ? "Answers use every source in this workspace."
                      : "Answers use this source only."}
                  </p>
                  <div className="space-y-1.5 pt-1">
                    {suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => sendSuggestion(suggestion)}
                        className="block w-full rounded-md border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground text-left leading-relaxed"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((msg, i) => (
                  <div
                    key={msg.id ?? `m-${i}`}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-lg px-3 py-2 text-[13px] leading-relaxed whitespace-pre-wrap ${
                        msg.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted"
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}
                {chatMutation.isPending && (
                  <div className="flex justify-start">
                    <div className="bg-muted rounded-lg px-3 py-2">
                      <div className="flex gap-1">
                        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse" />
                        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse [animation-delay:0.2s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse [animation-delay:0.4s]" />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t px-3 py-2.5 shrink-0">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex gap-2"
            >
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  isAllDatasets
                    ? "Question for the workspace…"
                    : "Question for this source…"
                }
                className="flex-1 text-sm h-9"
                disabled={chatMutation.isPending}
              />
              <Button
                type="submit"
                size="sm"
                className="h-9 px-3"
                disabled={chatMutation.isPending || !input.trim()}
              >
                Send
              </Button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
