"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { compliance as compApi, errorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { DISCIPLINES, type ComplianceRun, type ComplianceSet } from "@/lib/types";
import { VerdictBadge } from "@/components/VerdictBadge";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  Field,
  Input,
  Loading,
  Page,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";

export default function CompliancePage() {
  const router = useRouter();
  const [sets, setSets] = useState<ComplianceSet[] | null>(null);
  const [runs, setRuns] = useState<ComplianceRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([compApi.sets(), compApi.runs()]);
      setSets(s);
      setRuns(r);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setName = (id: string) => sets?.find((s) => s.id === id)?.name ?? id.slice(0, 8);

  return (
    <Page wide>
      <PageHeader
        title="Compliance"
        subtitle="Requirement sets and clause-by-clause checks of supplier documents."
        actions={
          <Button variant="primary" onClick={() => setShowCreate((s) => !s)}>
            {showCreate ? "Close" : "New requirement set"}
          </Button>
        }
      />
      {showCreate && (
        <div className="mb-4">
          <CreateSetForm
            onCreated={(s) => {
              setShowCreate(false);
              router.push(`/compliance/sets/${s.id}`);
            }}
          />
        </div>
      )}
      <ErrorBox error={error} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Requirement sets">
          {sets === null && !error ? (
            <Loading />
          ) : !sets || sets.length === 0 ? (
            <Empty>No requirement sets yet.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th>Discipline</Th>
                  <Th>Description</Th>
                </tr>
              </thead>
              <tbody>
                {sets.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <Td>
                      <Link href={`/compliance/sets/${s.id}`} className="font-medium text-slate-900 hover:underline">
                        {s.name}
                      </Link>
                    </Td>
                    <Td>{s.discipline && <Badge tone="blue">{s.discipline}</Badge>}</Td>
                    <Td className="text-xs text-slate-500">{s.description ?? ""}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        <Card title="Recent runs" actions={<Button size="sm" onClick={() => void load()}>Refresh</Button>}>
          {runs === null && !error ? (
            <Loading />
          ) : !runs || runs.length === 0 ? (
            <Empty>No runs yet. Start one from a document page.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Set</Th>
                  <Th>Status</Th>
                  <Th>Summary</Th>
                  <Th>Created</Th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <Td>
                      <Link href={`/compliance/runs/${r.id}`} className="font-medium text-slate-900 hover:underline">
                        {setName(r.set_id)}
                      </Link>
                      <div className="font-mono text-[11px] text-slate-400">
                        doc {r.subject_document_id.slice(0, 8)}…
                      </div>
                    </Td>
                    <Td>
                      <StatusBadge status={r.status} />
                    </Td>
                    <Td>
                      <SummaryInline summary={r.summary} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(r.created_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </Page>
  );
}

function SummaryInline({ summary }: { summary: ComplianceRun["summary"] }) {
  if (!summary?.counts) return <span className="text-xs text-slate-400">–</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {Object.entries(summary.counts)
        .filter(([, n]) => (n ?? 0) > 0)
        .map(([v, n]) => (
          <span key={v} className="inline-flex items-center gap-0.5">
            <VerdictBadge verdict={v} />
            <span className="text-xs tabular-nums text-slate-600">{n}</span>
          </span>
        ))}
    </div>
  );
}

function CreateSetForm({ onCreated }: { onCreated: (s: ComplianceSet) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await compApi.createSet({
        name: name.trim(),
        description: description.trim() || undefined,
        discipline: discipline || undefined,
      });
      onCreated(s);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="New requirement set">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-4">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Pump datasheet requirements" />
        </Field>
        <Field label="Discipline">
          <Select value={discipline} onChange={(e) => setDiscipline(e.target.value)}>
            <option value="">–</option>
            {DISCIPLINES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Description" className="md:col-span-2">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
        </Field>
        <div className="flex items-center gap-3 md:col-span-4">
          <Button type="submit" variant="primary" disabled={busy || !name.trim()}>
            {busy && <Spinner className="border-slate-500 border-t-white" />}
            Create
          </Button>
          <ErrorBox error={error} />
        </div>
      </form>
    </Card>
  );
}
