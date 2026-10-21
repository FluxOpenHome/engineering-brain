"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { documents as docsApi, errorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { DISCIPLINES, DOC_TYPES, type DocumentListItem } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";
import {
  Badge,
  Button,
  Card,
  ChipSelect,
  Empty,
  ErrorBox,
  Field,
  Input,
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

export default function DocumentsPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [project, setProject] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const load = useCallback(
    () => docsApi.list({ q: debouncedQ || undefined, project: project || undefined, limit: 200 }),
    [debouncedQ, project],
  );
  const { data, error, loading, refresh } = usePolling<DocumentListItem[]>(
    load,
    (d) => !!d?.some((x) => ACTIVE.has((x.parse_status ?? "").toLowerCase())),
    5000,
    [debouncedQ, project],
  );

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onQ = (v: string) => {
    setQ(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQ(v), 300);
  };

  const polling = !!data?.some((x) => ACTIVE.has((x.parse_status ?? "").toLowerCase()));

  return (
    <Page wide>
      <PageHeader
        title="Documents"
        subtitle="Upload engineering documents; parsing runs in the background."
        actions={
          <Button variant="primary" onClick={() => setShowUpload((s) => !s)}>
            {showUpload ? "Close" : "Upload document"}
          </Button>
        }
      />

      {showUpload && (
        <div className="mb-5">
          <UploadForm
            onDone={() => {
              setShowUpload(false);
              void refresh();
            }}
          />
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Field label="Search" className="w-72">
          <Input
            value={q}
            onChange={(e) => onQ(e.target.value)}
            placeholder="Title or document number…"
          />
        </Field>
        <Field label="Project" className="w-48">
          <Input value={project} onChange={(e) => setProject(e.target.value)} placeholder="Any" />
        </Field>
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
          {polling && (
            <>
              <Spinner /> parsing in progress, refreshing every 5 s
            </>
          )}
          <Button size="sm" onClick={() => void refresh()}>
            Refresh
          </Button>
        </div>
      </div>

      <ErrorBox error={error} />
      {loading && !data ? (
        <Loading />
      ) : !data || data.length === 0 ? (
        <Empty>No documents yet. Upload one to get started.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Title</Th>
              <Th>Doc number</Th>
              <Th>Rev</Th>
              <Th>Type</Th>
              <Th>Disciplines</Th>
              <Th>Parse</Th>
              <Th className="text-right">Pages</Th>
              <Th>Created</Th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr
                key={d.id}
                onClick={() => router.push(`/documents/${d.id}`)}
                className="cursor-pointer hover:bg-slate-50"
              >
                <Td className="font-medium text-slate-900">{d.title || <span className="text-slate-400">untitled</span>}</Td>
                <Td className="font-mono text-xs">{d.doc_number ?? ""}</Td>
                <Td>{d.current_revision ?? ""}</Td>
                <Td>{d.doc_type && <Badge>{d.doc_type}</Badge>}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {(d.discipline ?? []).map((x) => (
                      <Badge key={x} tone="blue">
                        {x}
                      </Badge>
                    ))}
                  </div>
                </Td>
                <Td>
                  <StatusBadge status={d.parse_status} />
                  {d.parse_pass != null && d.parse_pass > 0 && (
                    <span className="ml-1 text-xs text-slate-400">pass {d.parse_pass}</span>
                  )}
                </Td>
                <Td className="text-right tabular-nums">{d.page_count ?? ""}</Td>
                <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(d.created_at)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Page>
  );
}

function UploadForm({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [docNumber, setDocNumber] = useState("");
  const [revision, setRevision] = useState("");
  const [docType, setDocType] = useState<string>("spec");
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [project, setProject] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await docsApi.upload({
        file,
        title: title || undefined,
        doc_number: docNumber || undefined,
        revision: revision || undefined,
        doc_type: docType,
        discipline: disciplines,
        project: project || undefined,
      });
      setResult(
        res.duplicate
          ? `Duplicate detected; existing document ${res.document_id} reused.`
          : `Uploaded. Document ${res.document_id}; parse job ${res.job_id ?? "queued"}.`,
      );
      setTimeout(onDone, 800);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Upload document">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-3">
        <Field label="File" className="md:col-span-3">
          <input
            type="file"
            className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-50"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>
        <Field label="Title">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Defaults to filename" />
        </Field>
        <Field label="Document number">
          <Input value={docNumber} onChange={(e) => setDocNumber(e.target.value)} placeholder="e.g. PRJ-SPEC-001" />
        </Field>
        <Field label="Revision">
          <Input value={revision} onChange={(e) => setRevision(e.target.value)} placeholder="e.g. A, 01" />
        </Field>
        <Field label="Document type">
          <Select value={docType} onChange={(e) => setDocType(e.target.value)}>
            {DOC_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Project">
          <Input value={project} onChange={(e) => setProject(e.target.value)} placeholder="Optional" />
        </Field>
        <Field label="Disciplines" className="md:col-span-3">
          <ChipSelect options={DISCIPLINES} value={disciplines} onChange={setDisciplines} />
        </Field>
        <div className="flex items-center gap-3 md:col-span-3">
          <Button type="submit" variant="primary" disabled={busy || !file}>
            {busy ? <Spinner className="border-slate-500 border-t-white" /> : null}
            Upload
          </Button>
          <ErrorBox error={error} />
          {result && <Notice tone="green">{result}</Notice>}
        </div>
      </form>
    </Card>
  );
}
