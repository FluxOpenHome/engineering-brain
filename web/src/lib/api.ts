import type {
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  ComplianceRun,
  ComplianceRunDetail,
  ComplianceSet,
  ComplianceSetDetail,
  ConversationDetail,
  ConversationSummary,
  DocumentDetail,
  DocumentListItem,
  Finding,
  JobResponse,
  SearchRequest,
  SearchResponse,
  SpecCheckResponse,
  SpecDraftResponse,
  SpecTemplate,
  UploadResponse,
  UUID,
  WikiPage,
  WikiPagePut,
  WikiPageSummary,
  WikiProposal,
  WikiProposalSummary,
  WikiTreeNode,
} from "./types";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown = undefined;
  let message = `${res.status} ${res.statusText}`;
  try {
    const text = await res.text();
    try {
      const json = JSON.parse(text);
      detail = json;
      if (typeof json?.detail === "string") message = json.detail;
      else if (json?.detail) message = JSON.stringify(json.detail);
      else if (text) message = text;
    } catch {
      if (text) message = text;
    }
  } catch {
    // ignore
  }
  return new ApiError(res.status, message, detail);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (!isForm && init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("json")) return (await res.text()) as unknown as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

// ---------- Documents ----------

export interface UploadDocumentInput {
  file: File;
  title?: string;
  doc_number?: string;
  revision?: string;
  doc_type: string;
  discipline: string[];
  project?: string;
}

export const documents = {
  list: (params: { q?: string; project?: string; limit?: number; offset?: number } = {}) =>
    apiFetch<DocumentListItem[]>(`/documents${qs(params)}`),
  get: (id: UUID) => apiFetch<DocumentDetail>(`/documents/${id}`),
  remove: (id: UUID) => apiFetch<void>(`/documents/${id}`, { method: "DELETE" }),
  upload: (input: UploadDocumentInput) => {
    const fd = new FormData();
    fd.set("file", input.file);
    if (input.title) fd.set("title", input.title);
    if (input.doc_number) fd.set("doc_number", input.doc_number);
    if (input.revision) fd.set("revision", input.revision);
    fd.set("doc_type", input.doc_type);
    fd.set("discipline", input.discipline.join(","));
    if (input.project) fd.set("project", input.project);
    return apiFetch<UploadResponse>("/documents", { method: "POST", body: fd });
  },
};

// ---------- Search ----------

export const search = (req: SearchRequest) => apiFetch<SearchResponse>("/search", json(req));

// ---------- Chat ----------

export const chat = {
  ask: (req: ChatRequest) => apiFetch<ChatResponse>("/chat", json(req)),
  conversations: () => apiFetch<ConversationSummary[]>("/chat/conversations"),
  conversation: (id: UUID) => apiFetch<ConversationDetail>(`/chat/conversations/${id}`),
  /**
   * POST /chat/stream and parse the SSE body. EventSource cannot POST, so we read
   * the ReadableStream and split on blank lines; each block has `event:` and `data:`.
   */
  async *stream(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<ChatStreamEvent> {
    const res = await fetch(`${API_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal,
      cache: "no-store",
    });
    if (!res.ok) throw await parseError(res);
    if (!res.body) throw new ApiError(0, "stream has no body");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const flush = function* (block: string): Generator<ChatStreamEvent> {
      let event = "message";
      const dataLines: string[] = [];
      for (const raw of block.split("\n")) {
        const line = raw.replace(/\r$/, "");
        if (!line || line.startsWith(":")) continue;
        const idx = line.indexOf(":");
        const field = idx === -1 ? line : line.slice(0, idx);
        let value = idx === -1 ? "" : line.slice(idx + 1);
        if (value.startsWith(" ")) value = value.slice(1);
        if (field === "event") event = value;
        else if (field === "data") dataLines.push(value);
      }
      if (dataLines.length === 0) return;
      const dataStr = dataLines.join("\n");
      let data: unknown = dataStr;
      try {
        data = JSON.parse(dataStr);
      } catch {
        // keep as string
      }
      yield { event, data } as ChatStreamEvent;
    };
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const match = buffer.match(/\r?\n\r?\n/);
        const len = match ? match[0].length : 2;
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + len);
        yield* flush(block);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) yield* flush(buffer);
  },
};

// ---------- Wiki ----------

export const wiki = {
  pages: (params: { q?: string; status?: string; discipline?: string } = {}) =>
    apiFetch<WikiPageSummary[]>(`/wiki/pages${qs(params)}`),
  tree: () => apiFetch<WikiTreeNode>("/wiki/tree"),
  page: (slug: string) => apiFetch<WikiPage>(`/wiki/pages/${encodeSlug(slug)}`),
  put: (slug: string, body: WikiPagePut) =>
    apiFetch<WikiPage>(`/wiki/pages/${encodeSlug(slug)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  archive: (slug: string) =>
    apiFetch<void>(`/wiki/pages/${encodeSlug(slug)}`, { method: "DELETE" }),
  proposals: (status = "open") =>
    apiFetch<WikiProposalSummary[]>(`/wiki/proposals${qs({ status })}`),
  proposal: (id: UUID) => apiFetch<WikiProposal>(`/wiki/proposals/${id}`),
  accept: (id: UUID, body: { content?: string; note?: string }) =>
    apiFetch<{ page: WikiPage; stale_base: boolean }>(
      `/wiki/proposals/${id}/accept`,
      json(body),
    ),
  reject: (id: UUID, body: { note?: string }) =>
    apiFetch<{ ok: boolean }>(`/wiki/proposals/${id}/reject`, json(body)),
  propose: (revision_id: UUID) => apiFetch<JobResponse>("/wiki/propose", json({ revision_id })),
  reindex: () => apiFetch<JobResponse>("/wiki/reindex", { method: "POST" }),
  lint: () => apiFetch<unknown>("/wiki/lint"),
};

/** Slugs may contain `/`; keep separators but encode each segment. */
export function encodeSlug(slug: string): string {
  return slug
    .split("/")
    .filter(Boolean)
    .map((s) => encodeURIComponent(s))
    .join("/");
}

// ---------- Compliance ----------

export const compliance = {
  sets: () => apiFetch<ComplianceSet[]>("/compliance/sets"),
  createSet: (body: { name: string; description?: string; discipline?: string }) =>
    apiFetch<ComplianceSet>("/compliance/sets", json(body)),
  set: (id: UUID) => apiFetch<ComplianceSetDetail>(`/compliance/sets/${id}`),
  deleteSet: (id: UUID) => apiFetch<void>(`/compliance/sets/${id}`, { method: "DELETE" }),
  addRequirements: (
    id: UUID,
    requirements: { req_id: string; text: string; kind?: string; quantity?: unknown }[],
  ) => apiFetch<{ added: number }>(`/compliance/sets/${id}/requirements`, json({ requirements })),
  importFile: (id: UUID, file: File) => {
    const fd = new FormData();
    fd.set("file", file);
    return apiFetch<{ added: number }>(`/compliance/sets/${id}/import`, {
      method: "POST",
      body: fd,
    });
  },
  extract: (id: UUID, document_id: UUID) =>
    apiFetch<{ added: number }>(`/compliance/sets/${id}/extract`, json({ document_id })),
  createRun: (body: { set_id: UUID; document_id: UUID; revision_id?: UUID }) =>
    apiFetch<{ run_id: UUID; job_id: string }>("/compliance/runs", json(body)),
  runs: (set_id?: UUID) => apiFetch<ComplianceRun[]>(`/compliance/runs${qs({ set_id })}`),
  run: (id: UUID) => apiFetch<ComplianceRunDetail>(`/compliance/runs/${id}`),
  review: (findingId: UUID, body: { verdict: string; note?: string }) =>
    apiFetch<Finding | Record<string, unknown>>(
      `/compliance/findings/${findingId}/review`,
      json(body),
    ),
  exportUrl: (runId: UUID) => `${API_URL}/compliance/runs/${runId}/export.xlsx`,
};

// ---------- Specs ----------

export const specs = {
  templates: () => apiFetch<SpecTemplate[]>("/specs/templates"),
  check: (text: string) => apiFetch<SpecCheckResponse>("/specs/check", json({ text })),
  draft: (body: {
    template_key: string;
    project?: string;
    context?: string;
    document_ids?: UUID[];
  }) => apiFetch<SpecDraftResponse>("/specs/draft", json(body)),
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
