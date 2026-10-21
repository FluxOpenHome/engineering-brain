"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { errorMessage, wiki as wikiApi } from "@/lib/api";
import { fmtDate, pct } from "@/lib/format";
import type { WikiProposal } from "@/lib/types";
import { DiffView } from "@/components/DiffView";
import { Markdown } from "@/components/Markdown";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ErrorBox,
  Field,
  Input,
  Loading,
  Notice,
  Page,
  PageHeader,
  Spinner,
  StatusBadge,
  Tabs,
  Textarea,
} from "@/components/ui";

export default function ProposalPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [p, setP] = useState<WikiProposal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"diff" | "preview" | "current">("diff");
  const [editMode, setEditMode] = useState(false);
  const [edited, setEdited] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    wikiApi
      .proposal(id)
      .then((x) => {
        setP(x);
        setEdited(x.content);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [id]);

  const accept = async () => {
    if (!p) return;
    setBusy("accept");
    setError(null);
    try {
      const r = await wikiApi.accept(p.id, {
        content: editMode && edited !== p.content ? edited : undefined,
        note: note || undefined,
      });
      setDone(`Accepted and published to /wiki/${r.page?.slug ?? p.slug}.${r.stale_base ? " Base was stale; please verify the merged page." : ""}`);
      setP({ ...p, status: "accepted" });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const reject = async () => {
    if (!p) return;
    setBusy("reject");
    setError(null);
    try {
      await wikiApi.reject(p.id, { note: note || undefined });
      setDone("Rejected.");
      setP({ ...p, status: "rejected" });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (!p && !error) return <Page><Loading /></Page>;
  if (!p) return <Page><ErrorBox error={error} /></Page>;

  const open = p.status === "open";
  const proposedContent = editMode ? edited : p.content;

  return (
    <Page wide>
      <div className="mb-2 text-xs text-slate-500">
        <Link href="/review" className="hover:underline">
          Review
        </Link>{" "}
        / {p.id.slice(0, 8)}…
      </div>
      <PageHeader
        title={p.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={p.status} />
            <Badge tone={p.kind === "create" ? "green" : "blue"}>{p.kind}</Badge>
            <Link href={`/wiki/${p.slug}`} className="font-mono text-xs text-blue-700 hover:underline">
              /wiki/{p.slug}
            </Link>
            {p.confidence != null && (
              <Badge tone={p.confidence >= 0.8 ? "green" : p.confidence >= 0.5 ? "amber" : "red"}>
                confidence {pct(p.confidence)}
              </Badge>
            )}
            <span className="text-xs text-slate-400">
              {fmtDate(p.created_at)}
              {p.created_by ? ` · ${p.created_by}` : ""}
            </span>
          </span>
        }
        actions={
          open && (
            <>
              <Button variant="danger" onClick={reject} disabled={busy !== null}>
                {busy === "reject" && <Spinner />}
                Reject
              </Button>
              <Button variant="primary" onClick={accept} disabled={busy !== null}>
                {busy === "accept" && <Spinner className="border-slate-500 border-t-white" />}
                {editMode ? "Accept with edits" : "Accept"}
              </Button>
            </>
          )
        }
      />

      <div className="mb-4 space-y-2">
        {p.stale_base && (
          <Notice tone="amber">
            <strong>Stale base.</strong> The page changed after this proposal was drafted. The diff below is against the
            drafted base; review carefully or reject and re-propose.
          </Notice>
        )}
        {done && (
          <Notice tone="green">
            {done}{" "}
            <button type="button" className="underline" onClick={() => router.push("/review")}>
              Back to queue
            </button>
          </Notice>
        )}
        <ErrorBox error={error} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Tabs
              value={tab}
              onChange={setTab}
              tabs={[
                { key: "diff", label: "Diff" },
                { key: "preview", label: "Proposed (rendered)" },
                { key: "current", label: "Current page" },
              ]}
            />
            {open && (
              <Checkbox label="Edit before accepting" checked={editMode} onChange={setEditMode} />
            )}
          </div>
          {editMode && open && (
            <Textarea
              rows={18}
              value={edited}
              onChange={(e) => setEdited(e.target.value)}
              className="leading-5"
            />
          )}
          {tab === "diff" && <DiffView oldText={p.current_content ?? ""} newText={proposedContent} />}
          {tab === "preview" && (
            <Card>
              <Markdown>{proposedContent}</Markdown>
            </Card>
          )}
          {tab === "current" && (
            <Card>
              {p.current_content ? (
                <Markdown>{p.current_content}</Markdown>
              ) : (
                <div className="text-sm text-slate-500">Page does not exist yet (new page proposal).</div>
              )}
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="Rationale">
            <p className="whitespace-pre-wrap text-sm text-slate-700">{p.rationale || "–"}</p>
          </Card>
          <Card title={`Sources (${p.sources?.length ?? 0})`}>
            {!p.sources || p.sources.length === 0 ? (
              <div className="text-xs text-slate-400">No sources attached.</div>
            ) : (
              <ul className="space-y-2 text-xs">
                {p.sources.map((s, i) => {
                  const label = [s.doc_number, s.title].filter(Boolean).join(" — ") || s.document_id || "source";
                  const pg = s.page ?? s.page_start;
                  return (
                    <li key={i} className="rounded border border-slate-100 p-2">
                      {s.document_id ? (
                        <Link href={`/documents/${s.document_id}`} className="font-medium text-blue-700 hover:underline">
                          {label}
                        </Link>
                      ) : (
                        <span className="font-medium">{label}</span>
                      )}
                      <div className="mt-0.5 text-slate-500">
                        {s.revision && <span className="mr-2">Rev {s.revision}</span>}
                        {s.clause_id && <span className="mr-2">cl. {s.clause_id}</span>}
                        {pg != null && <span>p.{pg}</span>}
                      </div>
                      {typeof s.quote === "string" && s.quote && (
                        <blockquote className="mt-1 border-l-2 border-slate-200 pl-2 italic text-slate-600">
                          {s.quote}
                        </blockquote>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          {open && (
            <Card title="Review note">
              <Field label="Note (optional, saved with the decision)">
                <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. verified against Rev B" />
              </Field>
            </Card>
          )}
        </div>
      </div>
    </Page>
  );
}
