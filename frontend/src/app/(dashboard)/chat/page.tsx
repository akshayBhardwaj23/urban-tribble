"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatUserFacingApiError } from "@/lib/api-errors";
import { useWorkspace } from "@/lib/workspace-context";

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
  const [input, setInput] = useState("");
  const [requestedDataset, setRequestedDataset] = useState<string | null>(null);
  // Messages sent in this session, kept per conversation so switching source
  // (or workspace) never shows another conversation's turns.
  const [sentByConversation, setSentByConversation] = useState<
    Record<string, Message[]>
  >({});

  const { activeWorkspace, switching } = useWorkspace();
  const workspaceId = activeWorkspace?.id ?? "none";

  const { data: datasets, isLoading: loadingDatasets } = useQuery({
    queryKey: ["datasets-list", workspaceId],
    queryFn: () => api.listDatasets() as Promise<DatasetListItem[]>,
    enabled: !switching,
  });

  // A source removed in another tab should not leave a dangling selection.
  const selectedDataset =
    requestedDataset && datasets?.some((d) => d.id === requestedDataset)
      ? requestedDataset
      : datasets
        ? null
        : requestedDataset;

  const conversationKey = `${workspaceId}:${selectedDataset ?? "none"}`;

  const { data: historyData } = useQuery({
    queryKey: ["chat-history", workspaceId, selectedDataset, "dataset"],
    queryFn: () => api.getChatHistory(selectedDataset!),
    enabled: !!selectedDataset && !switching,
  });

  const messages = useMemo<Message[]>(() => {
    if (!selectedDataset) return [];
    const stored = (historyData ?? []).map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      content: m.content,
    }));
    return [...stored, ...(sentByConversation[conversationKey] ?? [])];
  }, [selectedDataset, historyData, sentByConversation, conversationKey]);

  const appendMessage = useCallback(
    (key: string, message: Message) => {
      setSentByConversation((prev) => ({
        ...prev,
        [key]: [...(prev[key] ?? []), message],
      }));
    },
    []
  );

  const chatMutation = useMutation({
    mutationFn: (question: string) => api.chat(selectedDataset!, question),
    onSuccess: (data, _question, context) => {
      appendMessage(context as string, {
        role: "assistant",
        content: data.answer,
      });
    },
    onError: (err: Error, _question, context) => {
      appendMessage(context as string, {
        role: "assistant",
        content: formatUserFacingApiError(err, "answer that question"),
      });
    },
    onMutate: () => conversationKey,
  });

  const handleSend = () => {
    if (!input.trim() || !selectedDataset) return;
    appendMessage(conversationKey, { role: "user", content: input });
    chatMutation.mutate(input);
    setInput("");
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-6rem)] max-w-5xl flex-col space-y-4">
      <div className="mb-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Q&A on your data
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Questions in plain language, scoped to one source-the answers use what you imported,
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
                    onClick={() => setRequestedDataset(ds.id)}
                    className="w-full rounded-2xl border border-white/70 bg-white/84 p-3 text-left text-sm transition-colors hover:bg-white dark:border-white/10 dark:bg-slate-900/70 dark:hover:bg-slate-900"
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
              onClick={() => setRequestedDataset(null)}
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
                        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                          msg.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-white/85 shadow-[0_12px_24px_-18px_rgba(15,23,42,0.22)] dark:bg-slate-900"
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
