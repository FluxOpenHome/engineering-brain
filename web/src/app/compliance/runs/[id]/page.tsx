"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { compliance as compApi, errorMessage } from "@/lib/api";
import { fmtDate, fmtQuantity, pct } from "@/lib/format";
import { VERDICTS, type ComplianceRunDetail, type Finding } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";
import { VERDICT_TONE, VerdictBadge } from "@/components/VerdictBadge";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ErrorBox,
  Field,
  Input,
  LinkButton,
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

const FINAL = new Set(["done", "failed"]);

export default function ComplianceRunPage() {
  const { id } = useParams<{ id: string }>();
  const load = useCallback(() => compApi.run(id), [id]);
  const { data, error, loading, refresh } = usePolling<ComplianceRunDetail>(
    load,
    (d) => !d || !FINAL.has((d.run.status ?? "").toLowerCase()),
    3000,
    [id],
  );
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [verdictFilter, setVerdictFilter] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());

  const findings = useMemo(() => {
    if (!data) return [];
    return data.findings.filter(
      (f) => (!needsReviewOnly || f.needs_review) && (!verdictFilter || effectiveVerdict(f) === verdictFilter),
    );
  }, [data, needsReviewOnly, verdictFilter]);

  if (loading && !data) return <Page><Loading /></Page>;
  if (error && !data) return <Page><ErrorBox error={error} /></Page>;
  if (!data) return null;

  const { run, summary } = data;
  const running = !FINAL.has((run.status ?? "").toLowerCase());
  const counts = summary?.counts ?? {};
  const guard = summary?.false_compliant_guard;
  const guardTripped = typeof guard === "number" ? guard > 0 : !!guard;
  const unrequested = summary?.unrequested_claims;
  const unrequestedList = Array.isArray(unrequested) ? unrequested : [];
  const unrequestedCount = Array.isArray(unrequested) ? unrequested.length : (unrequested ?? 0);

  const toggle = (fid: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(fid)) n.delete(fid);
      else n.add(fid);
      return n;
    });

  return (
    <Page wide>
      <div className="mb-2 text-xs text-slate-500">
        <Link href="/compliance" className="hover:underline">
          Compliance
        </Link>{" "}
        /{" "}
        <Link href={`/compliance/sets/${run.set_id}`} className="hover:underline">
          set {run.set_id.slice(0, 8)}…
        </Link>{" "}
        / run {run.id.slice(0, 8)}…
      </div>
      <PageHeader
        title="Compliance run"
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} />
            {running && (
              <span className="inline-flex items-center gap-1 text-xs">
                <Spinner /> refreshing every 3 s
              </span>
            )}
            <span>
              Subject:{" "}
              <Link href={`/documents/${run.subject_document_id}`} className="font-mono text-xs text-blue-700 hover:underline">
                {run.subject_document_id}
              </Link>
            </span>
            <span className="text-xs text-slate-400">
              started {fmtDate(run.created_at)}
              {run.finished_at ? `, finished ${fmtDate(run.finished_at)}` : ""}
            </span>
          </span>
        }
        actions={
          <>
            <Button onClick={() => void refresh()}>Refresh</Button>
            <LinkButton href={compApi.exportUrl(run.id)} external variant="primary">
              Export .xlsx
            </LinkButton>
          </>
        }
      />
      <ErrorBox error={error} />

      {/* Summary tiles */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        {VERDICTS.map((v) => (
          <Tile
            key={v}
            label={v.replace(/_/g, " ")}
            value={counts[v] ?? 0}
            tone={VERDICT_TONE[v]}
            active={verdictFilter === v}
            onClick={() => setVerdictFilter(verdictFilter === v ? "" : v)}
          />
        ))}
        <Tile
          label="needs review"
          value={summary?.needs_review ?? 0}
          tone="amber"
          active={needsReviewOnly}
          onClick={() => setNeedsReviewOnly((s) => !s)}
        />
        <Tile
          label="false-compliant guard"
          value={typeof guard === "number" ? guard : guardTripped ? "tripped" : "ok"}
          tone={guardTripped ? "red" : "green"}
        />
      </div>

      {guardTripped && (
        <div className="mb-4">
          <Notice tone="amber">
            The false-compliant guard changed one or more LLM &ldquo;compliant&rdquo; verdicts because a quote could not be
            verified or a numeric check failed. Those findings are routed to human review.
          </Notice>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <Checkbox label="Needs review only" checked={needsReviewOnly} onChange={setNeedsReviewOnly} />
        <Select value={verdictFilter} onChange={(e) => setVerdictFilter(e.target.value)} className="w-56">
          <option value="">All verdicts</option>
          {VERDICTS.map((v) => (
            <option key={v} value={v}>
              {v.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
        <span className="text-xs text-slate-500">
          {findings.length} of {data.findings.length} findings
        </span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" onClick={() => setOpen(new Set(findings.map((f) => f.id)))}>
            Expand all
          </Button>
          <Button size="sm" onClick={() => setOpen(new Set())}>
            Collapse all
          </Button>
        </div>
      </div>

      <Table>
        <thead>
          <tr>
            <Th className="w-28">Req</Th>
            <Th>Requirement</Th>
            <Th className="w-40">Verdict</Th>
            <Th className="w-24">Conf.</Th>
            <Th className="w-28">Evidence</Th>
            <Th className="w-28">Review</Th>
          </tr>
        </thead>
        <tbody>
          {findings.length === 0 && (
            <tr>
              <Td colSpan={6} className="py-8 text-center text-slate-500">
                {running ? "Findings appear as the run progresses." : "No findings match the filter."}
              </Td>
            </tr>
          )}
          {findings.map((f) => {
            const isOpen = open.has(f.id);
            return (
              <FindingRows key={f.id} finding={f} open={isOpen} onToggle={() => toggle(f.id)} onReviewed={() => void refresh()} />
            );
          })}
        </tbody>
      </Table>

      {unrequestedCount > 0 && (
        <Card title={`Unrequested claims (${unrequestedCount})`} className="mt-4">
          <p className="mb-2 text-xs text-slate-500">
            &ldquo;Shall&rdquo; statements in the subject document that match no requirement in the set.
          </p>
          {unrequestedList.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {unrequestedList.map((u, i) => (
                <li key={i} className="rounded border border-slate-100 p-2">
                  {u.text ?? u.quote ?? JSON.stringify(u)}
                  {u.page != null && <span className="ml-2 text-xs text-slate-400">p.{u.page}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-slate-500">Details available in the Excel export.</div>
          )}
        </Card>
      )}
    </Page>
  );
}

function effectiveVerdict(f: Finding): string {
  return f.reviewer_verdict ?? f.verdict;
}

function Tile({
  label,
  value,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: number | string;
  tone: keyof typeof toneBg;
  active?: boolean;
  onClick?: () => void;
}) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`rounded-lg border p-3 text-left ${toneBg[tone]} ${
        active ? "ring-2 ring-slate-900 ring-offset-1" : ""
      } ${onClick ? "cursor-pointer hover:brightness-95" : ""}`}
    >
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] uppercase tracking-wide opacity-80">{label}</div>
    </Comp>
  );
}

const toneBg = {
  green: "border-emerald-200 bg-emerald-50 text-emerald-900",
  red: "border-red-200 bg-red-50 text-red-900",
  amber: "border-amber-200 bg-amber-50 text-amber-900",
  grey: "border-gray-200 bg-gray-50 text-gray-700",
  purple: "border-purple-200 bg-purple-50 text-purple-900",
  slate: "border-slate-200 bg-slate-100 text-slate-700",
  blue: "border-blue-200 bg-blue-50 text-blue-900",
} as const;

function FindingRows({
  finding: f,
  open,
  onToggle,
  onReviewed,
}: {
  finding: Finding;
  open: boolean;
  onToggle: () => void;
  onReviewed: () => void;
}) {
  const verified = f.evidence.filter((e) => e.verified).length;
  const overridden = !!f.reviewer_verdict && f.reviewer_verdict !== f.verdict;
  return (
    <>
      <tr onClick={onToggle} className={`cursor-pointer hover:bg-slate-50 ${f.needs_review ? "bg-amber-50/40" : ""}`}>
        <Td className="whitespace-nowrap font-mono text-xs">{f.requirement.req_id}</Td>
        <Td>
          <div className={open ? "" : "line-clamp-2"}>{f.requirement.text}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {f.requirement.kind && <Badge tone="grey">{f.requirement.kind}</Badge>}
            {f.requirement.quantity && <Badge tone="slate">{fmtQuantity(f.requirement.quantity)}</Badge>}
          </div>
        </Td>
        <Td>
          <div className="flex flex-col gap-1">
            <VerdictBadge verdict={effectiveVerdict(f)} />
            {overridden && (
              <span className="text-[11px] text-slate-500">
                system: <VerdictBadge verdict={f.verdict} />
              </span>
            )}
            {f.llm_verdict && f.llm_verdict !== f.verdict && (
              <span className="text-[11px] text-slate-500">
                llm: <VerdictBadge verdict={f.llm_verdict} />
              </span>
            )}
          </div>
        </Td>
        <Td className="tabular-nums text-xs">{pct(f.confidence)}</Td>
        <Td className="text-xs">
          {f.evidence.length === 0 ? (
            <span className="text-slate-400">none</span>
          ) : (
            <span>
              {verified}/{f.evidence.length} verified
            </span>
          )}
        </Td>
        <Td>
          {f.needs_review && !f.reviewer_verdict && <Badge tone="amber">needs review</Badge>}
          {f.reviewer_verdict && <Badge tone="green">reviewed</Badge>}
        </Td>
      </tr>
      {open && (
        <tr>
          <Td colSpan={6} className="bg-slate-50">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <div className="space-y-3">
                <div>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Evidence</div>
                  {f.evidence.length === 0 ? (
                    <div className="text-sm text-slate-500">No evidence quoted.</div>
                  ) : (
                    <ul className="space-y-2">
                      {f.evidence.map((e, i) => (
                        <li
                          key={`${e.chunk_id}-${i}`}
                          className={`rounded border-l-4 bg-white p-2 text-sm ${
                            e.verified ? "border-emerald-400" : "border-red-400"
                          }`}
                        >
                          <blockquote className="whitespace-pre-wrap text-slate-800">&ldquo;{e.quote}&rdquo;</blockquote>
                          <div className="mt-1 flex gap-2 text-[11px] text-slate-500">
                            {e.page != null && <span>p.{e.page}</span>}
                            <Badge tone={e.verified ? "green" : "red"}>
                              {e.verified ? "verbatim verified" : "not found in chunk"}
                            </Badge>
                            {e.chunk_id && <span className="font-mono">{e.chunk_id.slice(0, 8)}…</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                {f.numeric_check && (
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Numeric check</div>
                    <NumericCheckView nc={f.numeric_check} />
                  </div>
                )}
                <div>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Rationale</div>
                  <p className="whitespace-pre-wrap text-sm text-slate-700">{f.rationale || "–"}</p>
                </div>
                {f.reviewer_note && (
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Reviewer note</div>
                    <p className="whitespace-pre-wrap text-sm text-slate-700">{f.reviewer_note}</p>
                  </div>
                )}
              </div>
              <ReviewForm finding={f} onReviewed={onReviewed} />
            </div>
          </Td>
        </tr>
      )}
    </>
  );
}

function NumericCheckView({ nc }: { nc: NonNullable<Finding["numeric_check"]> }) {
  const passed = nc.passed;
  const known = new Set(["passed", "expected", "found", "unit", "comparator", "message"]);
  const extra = Object.entries(nc).filter(([k, v]) => !known.has(k) && v != null);
  return (
    <div className="rounded border border-slate-200 bg-white p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {passed != null && <Badge tone={passed ? "green" : "red"}>{passed ? "pass" : "fail"}</Badge>}
        {nc.expected != null && (
          <span>
            expected <span className="font-mono">{nc.comparator ? `${nc.comparator} ` : ""}{String(nc.expected)}{nc.unit ? ` ${nc.unit}` : ""}</span>
          </span>
        )}
        {nc.found != null && (
          <span>
            found <span className="font-mono">{String(nc.found)}</span>
          </span>
        )}
      </div>
      {nc.message && <div className="mt-1 text-xs text-slate-600">{nc.message}</div>}
      {extra.length > 0 && (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-xs text-slate-500">
          {extra.map(([k, v]) => (
            <Fragment2 key={k} k={k} v={v} />
          ))}
        </dl>
      )}
    </div>
  );
}

function Fragment2({ k, v }: { k: string; v: unknown }) {
  return (
    <>
      <dt className="font-mono">{k}</dt>
      <dd className="font-mono">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
    </>
  );
}

function ReviewForm({ finding: f, onReviewed }: { finding: Finding; onReviewed: () => void }) {
  const [verdict, setVerdict] = useState<string>(f.reviewer_verdict ?? f.verdict);
  const [note, setNote] = useState(f.reviewer_note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    setError(null);
    try {
      await compApi.review(f.id, { verdict, note: note || undefined });
      setSaved(true);
      onReviewed();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2 rounded border border-slate-200 bg-white p-3" onClick={(e) => e.stopPropagation()}>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Reviewer override</div>
      <Field label="Verdict">
        <Select value={verdict} onChange={(e) => setVerdict(e.target.value)}>
          {VERDICTS.map((v) => (
            <option key={v} value={v}>
              {v.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Note">
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this verdict" />
      </Field>
      <Button type="submit" variant="primary" disabled={busy} className="w-full">
        {busy && <Spinner className="border-slate-500 border-t-white" />}
        Save review
      </Button>
      {saved && <div className="text-xs text-emerald-700">Saved.</div>}
      <ErrorBox error={error} />
    </form>
  );
}
