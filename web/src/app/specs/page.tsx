"use client";

import { useEffect, useMemo, useState } from "react";
import { errorMessage, specs as specsApi } from "@/lib/api";
import { splitCsv } from "@/lib/format";
import type {
  SpecCheckRequirement,
  SpecCheckResponse,
  SpecDraftResponse,
  SpecIssue,
  SpecTemplate,
} from "@/lib/types";
import { Markdown } from "@/components/Markdown";
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
  Table,
  Tabs,
  Td,
  Textarea,
  Th,
  type Tone,
} from "@/components/ui";

const SEVERITY_TONE: Record<string, Tone> = { error: "red", warning: "amber", info: "blue" };

export default function SpecsPage() {
  const [tab, setTab] = useState<"check" | "draft">("check");
  return (
    <Page>
      <PageHeader
        title="Specifications"
        subtitle="Check requirement sentences against INCOSE GtWR / EARS rules, or draft a specification from a template."
      />
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { key: "check", label: "Check" },
          { key: "draft", label: "Draft" },
        ]}
      />
      <div className="pt-4">{tab === "check" ? <CheckTab /> : <DraftTab />}</div>
    </Page>
  );
}

function IssueBadges({ issues }: { issues: SpecIssue[] }) {
  if (!issues || issues.length === 0) return <Badge tone="green">ok</Badge>;
  return (
    <div className="flex flex-wrap gap-1">
      {issues.map((i, k) => (
        <Badge key={k} tone={SEVERITY_TONE[i.severity] ?? "slate"} title={i.message}>
          {i.severity}: {i.rule}
        </Badge>
      ))}
    </div>
  );
}

function RequirementIssues({ reqs }: { reqs: SpecCheckRequirement[] }) {
  if (reqs.length === 0) return <Empty>No requirement sentences detected.</Empty>;
  return (
    <ol className="space-y-2">
      {reqs.map((r, i) => (
        <li key={i} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 w-6 shrink-0 text-right font-mono text-xs text-slate-400">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-900">{r.text}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                {r.ears_pattern && <Badge tone="purple">EARS: {r.ears_pattern}</Badge>}
                <IssueBadges issues={r.issues} />
              </div>
              {r.issues.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
                  {r.issues.map((iss, k) => (
                    <li key={k}>
                      <span className="font-mono text-slate-500">{iss.rule}</span> — {iss.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function CheckTab() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SpecCheckResponse | null>(null);

  const run = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await specsApi.check(text));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card title="Requirement text">
        <Textarea
          rows={10}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="!font-sans !text-sm"
          placeholder={"Paste one or more requirement sentences.\n\nWhen the suction pressure drops below 1.2 bar(a), the pump control system shall stop the pump within 2 s."}
        />
        <div className="mt-3 flex items-center gap-3">
          <Button variant="primary" onClick={run} disabled={busy || !text.trim()}>
            {busy && <Spinner className="border-slate-500 border-t-white" />}
            Check
          </Button>
          <ErrorBox error={error} />
        </div>
      </Card>
      {result && (
        <>
          {result.summary && Object.keys(result.summary).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(result.summary).map(([k, v]) => (
                <div key={k} className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm">
                  <span className="text-slate-500">{k.replace(/_/g, " ")}:</span>{" "}
                  <span className="font-semibold tabular-nums">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
          <RequirementIssues reqs={result.requirements} />
        </>
      )}
    </div>
  );
}

function DraftTab() {
  const [templates, setTemplates] = useState<SpecTemplate[] | null>(null);
  const [tplErr, setTplErr] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const [project, setProject] = useState("");
  const [context, setContext] = useState("");
  const [documentIds, setDocumentIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SpecDraftResponse | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    specsApi
      .templates()
      .then((t) => {
        setTemplates(t);
        if (t.length && !key) setKey(t[0].key);
      })
      .catch((e) => setTplErr(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tpl = useMemo(() => templates?.find((t) => t.key === key) ?? null, [templates, key]);

  const run = async () => {
    if (!key) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const ids = splitCsv(documentIds);
      setResult(
        await specsApi.draft({
          template_key: key,
          project: project || undefined,
          context: context || undefined,
          document_ids: ids.length ? ids : undefined,
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Clipboard access denied.");
    }
  };

  const draftIssues = result?.issues ?? [];
  const issuesAreRequirements = draftIssues.length > 0 && "text" in (draftIssues[0] as object);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <Card title="Template">
          {tplErr && <ErrorBox error={tplErr} />}
          {templates === null && !tplErr && <Loading />}
          {templates && (
            <div className="space-y-3">
              <Field label="Equipment class">
                <Select value={key} onChange={(e) => setKey(e.target.value)}>
                  {templates.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.name}
                      {t.discipline ? ` (${t.discipline})` : ""}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Project">
                <Input value={project} onChange={(e) => setProject(e.target.value)} placeholder="Optional" />
              </Field>
              <Field label="Document IDs" hint="Comma-separated; restricts parameter sourcing">
                <Input value={documentIds} onChange={(e) => setDocumentIds(e.target.value)} placeholder="Optional" />
              </Field>
              <Field label="Context">
                <Textarea
                  rows={4}
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  className="!font-sans !text-sm"
                  placeholder="Service, duty point, site conditions, applicable standards…"
                />
              </Field>
              <Button variant="primary" onClick={run} disabled={busy || !key} className="w-full">
                {busy && <Spinner className="border-slate-500 border-t-white" />}
                Draft specification
              </Button>
              <ErrorBox error={error} />
            </div>
          )}
        </Card>

        <div className="space-y-4">
          {tpl && (
            <Card title={`${tpl.name}: parameters (${tpl.parameters.length})`}>
              {tpl.standards_refs?.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {tpl.standards_refs.map((s) => (
                    <Badge key={s} tone="slate">
                      {s}
                    </Badge>
                  ))}
                </div>
              )}
              <Table>
                <thead>
                  <tr>
                    <Th>Parameter</Th>
                    <Th>Unit</Th>
                    <Th>Description</Th>
                    <Th>Flags</Th>
                  </tr>
                </thead>
                <tbody>
                  {tpl.parameters.map((p) => (
                    <tr key={p.name}>
                      <Td className="font-medium">{p.name}</Td>
                      <Td className="font-mono text-xs">{p.unit ?? ""}</Td>
                      <Td className="text-xs text-slate-600">{p.description ?? ""}</Td>
                      <Td>
                        <div className="flex gap-1">
                          {p.required && <Badge tone="red">required</Badge>}
                          {p.interface && <Badge tone="purple">interface</Badge>}
                        </div>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              {tpl.interface_checklist?.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Interface checklist
                  </div>
                  <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-700">
                    {tpl.interface_checklist.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}
        </div>
      </div>

      {result && (
        <div className="space-y-4">
          <Card
            title="Draft"
            actions={
              <Button size="sm" onClick={copy}>
                {copied ? "Copied" : "Copy markdown"}
              </Button>
            }
          >
            <Markdown>{result.markdown}</Markdown>
          </Card>
          <Card title={`Parameters (${result.parameters.length})`}>
            <Table>
              <thead>
                <tr>
                  <Th>Parameter</Th>
                  <Th>Value</Th>
                  <Th>Unit</Th>
                  <Th>Source</Th>
                  <Th>Note</Th>
                </tr>
              </thead>
              <tbody>
                {result.parameters.map((p, i) => (
                  <tr key={`${p.name}-${i}`}>
                    <Td className="font-medium">{p.name}</Td>
                    <Td className="font-mono text-xs">{p.value == null ? <span className="text-slate-400">TBD</span> : String(p.value)}</Td>
                    <Td className="font-mono text-xs">{p.unit ?? ""}</Td>
                    <Td className="text-xs text-slate-600">
                      {typeof p.source_citation === "string"
                        ? p.source_citation
                        : p.source_citation
                          ? [p.source_citation.doc_number, p.source_citation.revision && `Rev ${p.source_citation.revision}`, p.source_citation.clause_id && `cl. ${p.source_citation.clause_id}`, p.source_citation.page_start != null && `p.${p.source_citation.page_start}`]
                              .filter(Boolean)
                              .join(" ")
                          : ""}
                    </Td>
                    <Td className="text-xs text-slate-600">{p.note ?? ""}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
          <Card title={`Rule issues (${draftIssues.length})`}>
            {draftIssues.length === 0 ? (
              <Badge tone="green">No issues</Badge>
            ) : issuesAreRequirements ? (
              <RequirementIssues reqs={draftIssues as SpecCheckRequirement[]} />
            ) : (
              <ul className="space-y-1 text-sm">
                {(draftIssues as SpecIssue[]).map((iss, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <Badge tone={SEVERITY_TONE[iss.severity] ?? "slate"}>{iss.severity}</Badge>
                    <span>
                      <span className="font-mono text-xs text-slate-500">{iss.rule}</span> — {iss.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
