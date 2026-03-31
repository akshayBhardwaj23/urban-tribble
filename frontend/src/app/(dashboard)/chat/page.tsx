"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
}

interface DatasetListItem {
  id: string;
  name: string;
  row_count: number | null;
  column_count: number | null;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);

  const { data: datasets, isLoading: loadingDatasets } = useQuery({
    queryKey: ["datasets-list"],
    queryFn: () => api.listDatasets() as Promise<DatasetListItem[]>,
  });

  useEffect(() => {
    if (!datasets?.length || !selectedDataset) return;
    if (!datasets.some((d) => d.id === selectedDataset)) {
      setSelectedDataset(null);
      setMessages([]);
    }
  }, [datasets, selectedDataset]);

  const { data: historyData } = useQuery({
    queryKey: ["chat-history", selectedDataset, "dataset"],
    queryFn: () => api.getChatHistory(selectedDataset!),
    enabled: !!selectedDataset,
  });

  useEffect(() => {
    if (!selectedDataset) {
      setMessages([]);
      return;
    }
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
  }, [selectedDataset, historyData]);

  const chatMutation = useMutation({
    mutationFn: (question: string) => api.chat(selectedDataset!, question),
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

  const handleSend = () => {
    if (!input.trim() || !selectedDataset) return;
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    chatMutation.mutate(input);
    setInput("");
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-6rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight">Q&A on your data</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Questions in plain language, scoped to one source—the answers use what you imported,
          not the open web.
        </p>
      </div>

      {/* Dataset Selector */}
      {!selectedDataset ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Choose a source</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingDatasets ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : !datasets || datasets.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No sources yet. Import a file first.
              </p>
            ) : (
              <div className="space-y-2">
                {datasets.map((ds) => (
                  <button
                    key={ds.id}
                    onClick={() => setSelectedDataset(ds.id)}
                    className="w-full text-left rounded-md border p-3 text-sm transition-colors hover:bg-accent"
                  >
                    <p className="font-medium">{ds.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {ds.row_count?.toLocaleString()} rows · {ds.column_count}{" "}
                      columns
                    </p>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2">
            <p className="text-sm text-muted-foreground">
              Using:{" "}
              <span className="font-medium text-foreground">
                {datasets?.find((d) => d.id === selectedDataset)?.name}
              </span>
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelectedDataset(null);
                setMessages([]);
              }}
            >
              Change
            </Button>
          </div>

          <Card className="flex flex-1 flex-col overflow-hidden">
            <ScrollArea className="flex-1 p-4">
              {messages.length === 0 ? (
                <div className="flex h-full items-center justify-center py-20 text-center">
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Ask your first question</p>
                    <p className="text-xs text-muted-foreground max-w-xs">
                      For example: &quot;What was total revenue?&quot; or &quot;Which product had
                      the highest sales?&quot;
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((msg, i) => (
                    <div
                      key={msg.id ?? `m-${i}`}
                      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
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
                      <div className="bg-muted rounded-lg px-4 py-2">
                        <div className="flex gap-1">
                          <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse" />
                          <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse [animation-delay:0.2s]" />
                          <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse [animation-delay:0.4s]" />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </ScrollArea>
            <CardContent className="border-t p-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="flex gap-2"
              >
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask a question about this source..."
                  className="flex-1"
                  disabled={chatMutation.isPending}
                />
                <Button
                  type="submit"
                  size="sm"
                  disabled={chatMutation.isPending || !input.trim()}
                >
                  Send
                </Button>
              </form>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
