"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { compliance as compApi, documents as docsApi, errorMessage, wiki as wikiApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { ComplianceSet, DocumentDetail } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  Loading,
  Notice,
  Page,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";

const ACTIVE = new Set(["queued", "running"]);

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const load = useCallback(() => docsApi.get(id), [id]);
  const { data: doc, error, loading } = usePolling<DocumentDetail>(
    load,
    (d) => !!d && ACTIVE.has((d.parse_status ?? "").toLowerCase()),
    5000,
    [id],
  );

  const [msg, setMsg] = useState<string | null>(null);
  const [actErr, setActErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Compliance run picker
  const [showRun, setShowRun] = useState(false);
  const [sets, setSets] = useState<ComplianceSet[] | null>(null);
  const [setId, setSetId] = useState("");
  useEffect(() => {
    if (!showRun || sets) return;
    compApi.sets().then(setSets).catch((e) => setActErr(errorMessage(e)));
  }, [showRun, sets]);

  const currentRevisionId = (): string | null => {
    if (!doc) return null;
    const fromField = (doc.current_revision_id as string | null | undefined) ?? null;
    if (fromField) return fromField;
    const match = doc.revisions.find((r) => r.revision === doc.current_revision);
    return match?.id ?? doc.revisions[doc.revisions.length - 1]?.id ?? null;
  };

  const propose = async () => {
    const rev = currentRevisionId();
    if (!rev) {
      setActErr("No revision available to propose from.");
      return;
    }
    setBusy("propose");
    setActErr(null);
    try {
      const r = await wikiApi.propose(rev);
      setMsg(`Wiki proposal job queued (${r.job_id}). Results appear under Review.`);
    } catch (e) {
      setActErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const runCheck = async () => {
    if (!setId) return;
    setBusy("run");
    setActErr(null);
    try {
      const r = await compApi.createRun({ set_id: setId, document_id: id });
      router.push(`/compliance/runs/${r.run_id}`);
    } catch (e) {
      setActErr(errorMessage(e));
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!confirm("Delete this document and all its revisions?")) return;
    setBusy("delete");
    try {
      await docsApi.remove(id);
      router.push("/documents");
    } catch (e) {
      setActErr(errorMessage(e));
      setBusy(null);
    }
  };

  if (loading && !doc) return <Page><Loading /></Page>;
  if (error && !doc) return <Page><ErrorBox error={error} /></Page>;
  if (!doc) return null;

  return (
    <Page>
      <div className="mb-2 text-xs text-slate-500">
        <Link href="/documents" className="hover:underline">
          Documents
        </Link>{" "}
        / <span className="font-mono">{doc.doc_number ?? doc.id}</span>
      </div>
      <PageHeader
        title={doc.title || doc.filename || "Untitled document"}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            {doc.doc_number && <span className="font-mono">{doc.doc_number}</span>}
            {doc.current_revision && <span>Rev {doc.current_revision}</span>}
            {doc.doc_type && <Badge>{doc.doc_type}</Badge>}
            {(doc.discipline ?? []).map((d) => (
              <Badge key={d} tone="blue">
                {d}
              </Badge>
            ))}
            {doc.project && <Badge tone="purple">{doc.project}</Badge>}
          </span>
        }
        actions={
          <>
            <Button variant="primary" onClick={propose} disabled={busy !== null}>
              {busy === "propose" && <Spinner className="border-slate-500 border-t-white" />}
              Propose wiki updates
            </Button>
            <Button onClick={() => setShowRun((s) => !s)} disabled={busy !== null}>
              Run compliance check
            </Button>
            <Button variant="danger" onClick={remove} disabled={busy !== null}>
              Delete
            </Button>
          </>
        }
      />

      {showRun && (
        <Card title="Run compliance check" className="mb-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-96">
              <div className="mb-1 text-xs font-medium text-slate-600">Requirement set</div>
              {sets === null ? (
                <Loading label="Loading sets" />
              ) : (
                <Select value={setId} onChange={(e) => setSetId(e.target.value)}>
                  <option value="">Select a set…</option>
                  {sets.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                      {s.discipline ? ` (${s.discipline})` : ""}
                    </option>
                  ))}
                </Select>
              )}
            </div>
            <Button variant="primary" onClick={runCheck} disabled={!setId || busy !== null}>
              {busy === "run" && <Spinner className="border-slate-500 border-t-white" />}
              Start run
            </Button>
            <Link href="/compliance" className="text-sm text-blue-700 hover:underline">
              Manage sets
            </Link>
          </div>
        </Card>
      )}

      <div className="mb-4 space-y-2">
        <ErrorBox error={actErr} />
        {msg && <Notice tone="green">{msg}</Notice>}
        {error && <ErrorBox error={error} />}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Details" className="md:col-span-1">
          <dl className="space-y-2 text-sm">
            <Row k="Parse status">
              <StatusBadge status={doc.parse_status} />
              {ACTIVE.has((doc.parse_status ?? "").toLowerCase()) && (
                <span className="ml-2 inline-flex items-center gap-1 text-xs text-slate-500">
                  <Spinner /> refreshing
                </span>
              )}
            </Row>
            <Row k="Parse pass">{doc.parse_pass ?? "–"}</Row>
            <Row k="Pages">{doc.page_count ?? "–"}</Row>
            <Row k="Revision status">
              <StatusBadge status={doc.revision_status} />
            </Row>
            <Row k="Filename">
              <span className="break-all font-mono text-xs">{doc.filename ?? "–"}</span>
            </Row>
            <Row k="MIME">
              <span className="font-mono text-xs">{doc.mime ?? "–"}</span>
            </Row>
            <Row k="Created">{fmtDate(doc.created_at)}</Row>
            <Row k="ID">
              <span className="break-all font-mono text-xs">{doc.id}</span>
            </Row>
          </dl>
        </Card>

        <Card title="Revisions" className="md:col-span-2">
          {doc.revisions.length === 0 ? (
            <div className="text-sm text-slate-500">No revisions.</div>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Rev</Th>
                  <Th>Status</Th>
                  <Th>Parse</Th>
                  <Th>Pass</Th>
                  <Th className="text-right">Pages</Th>
                  <Th>Created</Th>
                  <Th>ID</Th>
                </tr>
              </thead>
              <tbody>
                {doc.revisions.map((r) => (
                  <tr key={r.id} className={r.revision === doc.current_revision ? "bg-slate-50" : ""}>
                    <Td className="font-medium">{r.revision ?? "–"}</Td>
                    <Td>
                      <StatusBadge status={r.status} />
                    </Td>
                    <Td>
                      <StatusBadge status={r.parse_status} />
                    </Td>
                    <Td>{r.parse_pass ?? "–"}</Td>
                    <Td className="text-right tabular-nums">{r.page_count ?? "–"}</Td>
                    <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(r.created_at)}</Td>
                    <Td className="font-mono text-[11px] text-slate-400">{r.id.slice(0, 8)}…</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>

      <div className="mt-4 flex gap-3 text-sm">
        <Link
          href={`/search?document_ids=${doc.id}`}
          className="text-blue-700 hover:underline"
        >
          Search within this document
        </Link>
        <Link href={`/chat?document_ids=${doc.id}`} className="text-blue-700 hover:underline">
          Ask about this document
        </Link>
      </div>
    </Page>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-slate-500">{k}</dt>
      <dd className="text-right text-slate-900">{children}</dd>
    </div>
  );
}
