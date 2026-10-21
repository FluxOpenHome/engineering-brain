"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { compliance as compApi, errorMessage } from "@/lib/api";
import { fmtDate, fmtQuantity } from "@/lib/format";
import type { ComplianceRun, ComplianceSetDetail, DocumentListItem } from "@/lib/types";
import { DocumentPicker } from "@/components/DocumentPicker";
import {
  Badge,
  Button,
  Card,
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
  Tabs,
  Td,
  Textarea,
  Th,
} from "@/components/ui";

type AddTab = "manual" | "import" | "extract";

export default function ComplianceSetPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<ComplianceSetDetail | null>(null);
  const [runs, setRuns] = useState<ComplianceRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [tab, setTab] = useState<AddTab>("manual");

  const load = useCallback(async () => {
    try {
      const [d, r] = await Promise.all([compApi.set(id), compApi.runs(id)]);
      setDetail(d);
      setRuns(r);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const deleteSet = async () => {
    if (!detail || !confirm(`Delete set "${detail.set.name}" and its requirements?`)) return;
    try {
      await compApi.deleteSet(id);
      router.push("/compliance");
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  // Run against document
  const [runDoc, setRunDoc] = useState("");
  const [runBusy, setRunBusy] = useState(false);
  const startRun = async () => {
    if (!runDoc) return;
    setRunBusy(true);
    try {
      const r = await compApi.createRun({ set_id: id, document_id: runDoc });
      router.push(`/compliance/runs/${r.run_id}`);
    } catch (e) {
      setError(errorMessage(e));
      setRunBusy(false);
    }
  };

  if (!detail && !error) return <Page><Loading /></Page>;
  if (!detail) return <Page><ErrorBox error={error} /></Page>;

  const onAdded = (n: number, how: string) => {
    setMsg(`${n} requirement${n === 1 ? "" : "s"} added via ${how}.`);
    void load();
  };

  return (
    <Page wide>
      <div className="mb-2 text-xs text-slate-500">
        <Link href="/compliance" className="hover:underline">
          Compliance
        </Link>{" "}
        / {detail.set.name}
      </div>
      <PageHeader
        title={detail.set.name}
        subtitle={
          <span className="flex items-center gap-2">
            {detail.set.discipline && <Badge tone="blue">{detail.set.discipline}</Badge>}
            {detail.set.description}
            <span className="text-xs text-slate-400">{detail.requirements.length} requirements</span>
          </span>
        }
        actions={
          <Button variant="danger" onClick={deleteSet}>
            Delete set
          </Button>
        }
      />
      <div className="mb-4 space-y-2">
        <ErrorBox error={error} />
        {msg && <Notice tone="green">{msg}</Notice>}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Card title="Requirements">
            {detail.requirements.length === 0 ? (
              <Empty>No requirements yet. Add them manually, import a file, or extract from a document.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Req ID</Th>
                    <Th>Text</Th>
                    <Th>Kind</Th>
                    <Th>Quantity</Th>
                    <Th>EARS</Th>
                  </tr>
                </thead>
                <tbody>
                  {detail.requirements.map((r) => (
                    <tr key={r.id}>
                      <Td className="whitespace-nowrap font-mono text-xs">{r.req_id}</Td>
                      <Td className="text-slate-800">{r.text}</Td>
                      <Td>{r.kind && <Badge>{r.kind}</Badge>}</Td>
                      <Td className="font-mono text-xs text-slate-600">{fmtQuantity(r.quantity)}</Td>
                      <Td className="text-xs text-slate-500">{r.ears_pattern ?? ""}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <Card title="Runs against this set">
            {runs === null ? (
              <Loading />
            ) : runs.length === 0 ? (
              <div className="text-sm text-slate-500">No runs yet.</div>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Run</Th>
                    <Th>Subject document</Th>
                    <Th>Status</Th>
                    <Th>Needs review</Th>
                    <Th>Created</Th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="hover:bg-slate-50">
                      <Td>
                        <Link href={`/compliance/runs/${r.id}`} className="font-mono text-xs text-blue-700 hover:underline">
                          {r.id.slice(0, 8)}…
                        </Link>
                      </Td>
                      <Td>
                        <Link href={`/documents/${r.subject_document_id}`} className="font-mono text-xs hover:underline">
                          {r.subject_document_id.slice(0, 8)}…
                        </Link>
                      </Td>
                      <Td>
                        <StatusBadge status={r.status} />
                      </Td>
                      <Td className="tabular-nums">{r.summary?.needs_review ?? ""}</Td>
                      <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(r.created_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Run compliance check">
            <div className="space-y-2">
              <DocumentPicker value={runDoc} onChange={(v) => setRunDoc(v)} placeholder="Find subject document…" />
              <Button variant="primary" onClick={startRun} disabled={!runDoc || runBusy} className="w-full">
                {runBusy && <Spinner className="border-slate-500 border-t-white" />}
                Start run
              </Button>
            </div>
          </Card>

          <Card title="Add requirements">
            <Tabs
              value={tab}
              onChange={setTab}
              tabs={[
                { key: "manual", label: "Manual" },
                { key: "import", label: "Import" },
                { key: "extract", label: "Extract" },
              ]}
            />
            <div className="pt-3">
              {tab === "manual" && <ManualAdd setId={id} onAdded={(n) => onAdded(n, "manual entry")} />}
              {tab === "import" && <ImportAdd setId={id} onAdded={(n) => onAdded(n, "file import")} />}
              {tab === "extract" && <ExtractAdd setId={id} onAdded={(n) => onAdded(n, "document extraction")} />}
            </div>
          </Card>
        </div>
      </div>
    </Page>
  );
}

function ManualAdd({ setId, onAdded }: { setId: string; onAdded: (n: number) => void }) {
  const [reqId, setReqId] = useState("");
  const [text, setText] = useState("");
  const [kind, setKind] = useState("");
  const [bulk, setBulk] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const items: { req_id: string; text: string; kind?: string }[] = [];
    if (bulk.trim()) {
      // One requirement per line: "REQ-001<TAB or |>text" or just text.
      bulk.split("\n").forEach((line, i) => {
        const l = line.trim();
        if (!l) return;
        const m = l.match(/^([A-Za-z0-9._-]+)\s*[\t|]\s*(.+)$/);
        if (m) items.push({ req_id: m[1], text: m[2].trim() });
        else items.push({ req_id: `R-${String(i + 1).padStart(3, "0")}`, text: l });
      });
    } else if (text.trim()) {
      items.push({ req_id: reqId.trim() || "R-001", text: text.trim(), kind: kind || undefined });
    }
    if (items.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const r = await compApi.addRequirements(setId, items);
      onAdded(r.added);
      setReqId("");
      setText("");
      setBulk("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <Field label="Req ID">
        <Input value={reqId} onChange={(e) => setReqId(e.target.value)} placeholder="REQ-001" />
      </Field>
      <Field label="Requirement text">
        <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} className="!font-sans !text-sm" placeholder="The pump shall deliver 120 m3/h at 45 m head." />
      </Field>
      <Field label="Kind">
        <Select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">auto</option>
          <option value="functional">functional</option>
          <option value="performance">performance</option>
          <option value="interface">interface</option>
          <option value="design">design</option>
          <option value="documentation">documentation</option>
        </Select>
      </Field>
      <Field label="Or paste many" hint="One per line: ID | text">
        <Textarea rows={4} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder={"REQ-001 | The pump shall…\nREQ-002 | The motor shall…"} />
      </Field>
      <Button type="submit" variant="primary" disabled={busy || (!text.trim() && !bulk.trim())} className="w-full">
        {busy && <Spinner className="border-slate-500 border-t-white" />}
        Add
      </Button>
      <ErrorBox error={error} />
    </form>
  );
}

function ImportAdd({ setId, onAdded }: { setId: string; onAdded: (n: number) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const r = await compApi.importFile(setId, file);
      onAdded(r.added);
      setFile(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2">
      <Field label="Spreadsheet (.xlsx or .csv)" hint="Columns: req_id, text, optional kind, quantity">
        <input
          type="file"
          accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </Field>
      <Button type="submit" variant="primary" disabled={busy || !file} className="w-full">
        {busy && <Spinner className="border-slate-500 border-t-white" />}
        Import
      </Button>
      <ErrorBox error={error} />
    </form>
  );
}

function ExtractAdd({ setId, onAdded }: { setId: string; onAdded: (n: number) => void }) {
  const [docId, setDocId] = useState("");
  const [doc, setDoc] = useState<DocumentListItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    if (!docId) return;
    setBusy(true);
    setError(null);
    try {
      const r = await compApi.extract(setId, docId);
      onAdded(r.added);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <div className="text-xs text-slate-500">
        Extract &ldquo;shall&rdquo; statements from an ingested specification into this set.
      </div>
      <DocumentPicker
        value={docId}
        onChange={(v, d) => {
          setDocId(v);
          setDoc(d);
        }}
        placeholder="Find specification…"
      />
      {doc && doc.parse_status !== "done" && (
        <Notice tone="amber">Parse status is {doc.parse_status ?? "unknown"}; extraction may be incomplete.</Notice>
      )}
      <Button variant="primary" onClick={run} disabled={!docId || busy} className="w-full">
        {busy && <Spinner className="border-slate-500 border-t-white" />}
        Extract requirements
      </Button>
      <ErrorBox error={error} />
    </div>
  );
}
