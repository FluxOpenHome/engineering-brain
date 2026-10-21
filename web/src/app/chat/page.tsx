"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chat as chatApi, errorMessage } from "@/lib/api";
import { citationLabel, fmtDate, splitCsv } from "@/lib/format";
import type { Citation, ConversationSummary, Hit, Usage } from "@/lib/types";
import { HitCard } from "@/components/HitCard";
import { Markdown } from "@/components/Markdown";
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Input,
  Loading,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";

type Scope = "both" | "documents" | "wiki";

interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  sources: Hit[];
  usage?: Usage | null;
  model?: string | null;
  streaming?: boolean;
  error?: string | null;
}

export default function ChatPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ChatInner />
    </Suspense>
  );
}

function ChatInner() {
  const sp = useSearchParams();
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [convErr, setConvErr] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loadingConv, setLoadingConv] = useState(false);

  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState<Scope>("both");
  const [project, setProject] = useState(sp.get("project") ?? "");
  const [documentIds, setDocumentIds] = useState(sp.get("document_ids") ?? "");
  const [busy, setBusy] = useState(false);
  const [activeMsgId, setActiveMsgId] = useState<string | null>(null);
  const [highlightChunk, setHighlightChunk] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadConversations = useCallback(async () => {
    try {
      setConversations(await chatApi.conversations());
      setConvErr(null);
    } catch (e) {
      setConvErr(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  const lastContentLength = messages[messages.length - 1]?.content.length ?? 0;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastContentLength]);

  const openConversation = async (id: string) => {
    abortRef.current?.abort();
    setConversationId(id);
    setLoadingConv(true);
    try {
      const d = await chatApi.conversation(id);
      const msgs: Msg[] = d.messages.map((m) => ({
        id: m.id,
        role: m.role === "assistant" ? "assistant" : "user",
        content: m.content,
        citations: m.citations ?? [],
        sources: [],
        usage: m.usage,
      }));
      setMessages(msgs);
      const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant");
      setActiveMsgId(lastAssistant?.id ?? null);
    } catch (e) {
      setMessages([{ id: "err", role: "assistant", content: "", citations: [], sources: [], error: errorMessage(e) }]);
    } finally {
      setLoadingConv(false);
    }
  };

  const newConversation = () => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    setActiveMsgId(null);
    setHighlightChunk(null);
  };

  const updateMsg = (id: string, patch: Partial<Msg> | ((m: Msg) => Partial<Msg>)) =>
    setMessages((ms) =>
      ms.map((m) => (m.id === id ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)),
    );

  const send = async () => {
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    const userId = `u-${Date.now()}`;
    const asstId = `a-${Date.now()}`;
    setMessages((ms) => [
      ...ms,
      { id: userId, role: "user", content: q, citations: [], sources: [] },
      { id: asstId, role: "assistant", content: "", citations: [], sources: [], streaming: true },
    ]);
    setActiveMsgId(asstId);
    setHighlightChunk(null);

    const ids = splitCsv(documentIds);
    const body = {
      question: q,
      conversation_id: conversationId,
      document_ids: ids.length ? ids : undefined,
      project: project || null,
      include_documents: scope !== "wiki",
      include_wiki: scope !== "documents",
    };

    const ac = new AbortController();
    abortRef.current = ac;
    let gotDelta = false;
    let newConvId: string | null = null;
    try {
      for await (const ev of chatApi.stream(body, ac.signal)) {
        switch (ev.event) {
          case "conversation": {
            const d = ev.data as { conversation_id: string };
            newConvId = d.conversation_id;
            setConversationId(d.conversation_id);
            break;
          }
          case "sources": {
            const hits = Array.isArray(ev.data) ? (ev.data as Hit[]) : [];
            updateMsg(asstId, { sources: hits });
            break;
          }
          case "delta": {
            gotDelta = true;
            const d = ev.data as { text: string };
            updateMsg(asstId, (m) => ({ content: m.content + (d.text ?? "") }));
            break;
          }
          case "done": {
            const d = ev.data as { citations?: Citation[]; usage?: Usage; model?: string };
            updateMsg(asstId, {
              citations: d.citations ?? [],
              usage: d.usage ?? null,
              model: d.model ?? null,
              streaming: false,
            });
            break;
          }
          case "error": {
            const d = ev.data as { message?: string; detail?: string };
            throw new Error(d.message ?? d.detail ?? "stream error");
          }
          default:
            break;
        }
      }
      updateMsg(asstId, { streaming: false });
    } catch (e) {
      if (ac.signal.aborted) {
        updateMsg(asstId, { streaming: false });
      } else if (!gotDelta) {
        // Fallback to the non-streaming endpoint.
        try {
          const r = await chatApi.ask(body);
          newConvId = r.conversation_id;
          setConversationId(r.conversation_id);
          updateMsg(asstId, {
            content: r.answer,
            citations: r.citations,
            sources: r.sources,
            usage: r.usage,
            model: r.model,
            streaming: false,
          });
        } catch (e2) {
          updateMsg(asstId, { streaming: false, error: `${errorMessage(e)} — fallback: ${errorMessage(e2)}` });
        }
      } else {
        updateMsg(asstId, { streaming: false, error: errorMessage(e) });
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
      if (newConvId && !conversations?.some((c) => c.id === newConvId)) void loadConversations();
    }
  };

  const activeMsg = useMemo(
    () => messages.find((m) => m.id === activeMsgId) ?? [...messages].reverse().find((m) => m.role === "assistant"),
    [messages, activeMsgId],
  );

  const jumpToCitation = (msg: Msg, c: Citation) => {
    setActiveMsgId(msg.id);
    const key = c.chunk_id ?? `cite-${c.index}`;
    setHighlightChunk(key);
    requestAnimationFrame(() => {
      document.getElementById(`source-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  return (
    <div className="flex h-screen">
      {/* Conversations */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5">
          <span className="text-sm font-semibold">Conversations</span>
          <Button size="sm" variant="primary" onClick={newConversation}>
            New
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {convErr && <div className="px-1 text-xs text-red-600">{convErr}</div>}
          {conversations === null && !convErr && <Loading />}
          {conversations?.length === 0 && (
            <div className="px-2 py-4 text-xs text-slate-400">No conversations yet.</div>
          )}
          {conversations?.map((c) => (
            <button
              type="button"
              key={c.id}
              onClick={() => void openConversation(c.id)}
              className={`mb-0.5 block w-full rounded-md px-2.5 py-2 text-left text-sm hover:bg-slate-100 ${
                c.id === conversationId ? "bg-slate-100 font-medium" : ""
              }`}
            >
              <div className="truncate text-slate-800">{c.title || "Untitled"}</div>
              <div className="text-[11px] text-slate-400">{fmtDate(c.created_at)}</div>
            </button>
          ))}
        </div>
      </aside>

      {/* Main */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
          <Select value={scope} onChange={(e) => setScope(e.target.value as Scope)} className="w-44">
            <option value="both">Documents + wiki</option>
            <option value="documents">Documents only</option>
            <option value="wiki">Wiki only</option>
          </Select>
          <Input
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="Project (optional)"
            className="w-44"
          />
          <Input
            value={documentIds}
            onChange={(e) => setDocumentIds(e.target.value)}
            placeholder="Document IDs, comma-separated (optional)"
            className="min-w-64 flex-1"
          />
          {conversationId && (
            <span className="font-mono text-[11px] text-slate-400" title="conversation id">
              {conversationId.slice(0, 8)}…
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {loadingConv ? (
            <Loading label="Loading conversation" />
          ) : messages.length === 0 ? (
            <Empty>
              Ask a question over the corpus. Answers cite documents at page level.
            </Empty>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-slate-900 px-4 py-2 text-sm text-white">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div
                    key={m.id}
                    onClick={() => setActiveMsgId(m.id)}
                    className={`rounded-lg border bg-white p-4 ${
                      activeMsg?.id === m.id ? "border-slate-400" : "border-slate-200"
                    }`}
                  >
                    {m.error && <ErrorBox error={m.error} />}
                    {m.content ? (
                      <Markdown>{m.content}</Markdown>
                    ) : m.streaming ? (
                      <div className="flex items-center gap-2 text-sm text-slate-500">
                        <Spinner /> Retrieving and drafting…
                      </div>
                    ) : null}
                    {m.streaming && m.content && (
                      <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-slate-400 align-middle" />
                    )}
                    {!m.streaming && m.citations.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3">
                        {m.citations.map((c) => (
                          <button
                            type="button"
                            key={`${m.id}-${c.index}-${c.chunk_id}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              jumpToCitation(m, c);
                            }}
                            title={c.cited_text ?? undefined}
                            className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700 hover:border-amber-400 hover:bg-amber-50"
                          >
                            <span className="font-semibold">[{c.index}]</span>
                            {citationLabel(c)}
                          </button>
                        ))}
                      </div>
                    )}
                    {!m.streaming && (m.usage || m.model) && (
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-400">
                        {m.model && <span>{m.model}</span>}
                        {m.usage &&
                          Object.entries(m.usage).map(([k, v]) => (
                            <span key={k}>
                              {k}: {v}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                ),
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 bg-white p-3">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <Textarea
              rows={2}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
              className="!font-sans !text-sm"
            />
            {busy ? (
              <Button variant="danger" onClick={() => abortRef.current?.abort()}>
                Stop
              </Button>
            ) : (
              <Button variant="primary" onClick={() => void send()} disabled={!question.trim()}>
                Send
              </Button>
            )}
          </div>
        </div>
      </section>

      {/* Sources */}
      <aside className="flex w-96 shrink-0 flex-col border-l border-slate-200 bg-slate-50">
        <div className="border-b border-slate-200 bg-white px-3 py-2.5 text-sm font-semibold">
          Sources
          {activeMsg && activeMsg.sources.length > 0 && (
            <span className="ml-2 text-xs font-normal text-slate-500">{activeMsg.sources.length} retrieved</span>
          )}
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {!activeMsg ? (
            <div className="text-xs text-slate-400">Retrieved passages for the current answer appear here.</div>
          ) : activeMsg.sources.length > 0 ? (
            activeMsg.sources.map((h, i) => {
              const cited = activeMsg.citations.filter((c) => c.chunk_id === h.id).map((c) => c.index);
              return (
                <div key={h.id} className="relative">
                  {cited.length > 0 && (
                    <div className="absolute -top-1.5 right-2 z-10 flex gap-1">
                      {cited.map((n) => (
                        <Badge key={n} tone="amber">
                          [{n}]
                        </Badge>
                      ))}
                    </div>
                  )}
                  <HitCard
                    id={`source-${h.id}`}
                    hit={h}
                    index={i + 1}
                    compact
                    highlighted={highlightChunk === h.id}
                  />
                </div>
              );
            })
          ) : activeMsg.citations.length > 0 ? (
            // Historical messages carry citations but no retrieved hits.
            activeMsg.citations.map((c) => (
              <div
                key={`cite-${c.index}`}
                id={`source-${c.chunk_id ?? `cite-${c.index}`}`}
                className={`rounded-lg border bg-white p-3 text-sm ${
                  highlightChunk === (c.chunk_id ?? `cite-${c.index}`)
                    ? "border-amber-400 shadow-[0_0_0_3px_rgba(251,191,36,0.35)]"
                    : "border-slate-200"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="amber">[{c.index}]</Badge>
                  <Badge tone={c.source === "wiki" ? "purple" : "blue"}>{c.source}</Badge>
                  <span className="font-medium">{citationLabel(c)}</span>
                </div>
                {c.cited_text && <p className="mt-2 text-xs text-slate-700">{c.cited_text}</p>}
              </div>
            ))
          ) : (
            <div className="text-xs text-slate-400">No sources for this message.</div>
          )}
        </div>
      </aside>
    </div>
  );
}
