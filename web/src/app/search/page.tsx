"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { errorMessage, search as searchApi } from "@/lib/api";
import { splitCsv } from "@/lib/format";
import { DISCIPLINES, DOC_TYPES, type SearchResponse } from "@/lib/types";
import { HitCard } from "@/components/HitCard";
import {
  Button,
  Checkbox,
  ChipSelect,
  Empty,
  ErrorBox,
  Field,
  Input,
  Loading,
  Page,
  PageHeader,
  Spinner,
} from "@/components/ui";

export default function SearchPage() {
  return (
    <Suspense fallback={<Page><Loading /></Page>}>
      <SearchInner />
    </Suspense>
  );
}

function SearchInner() {
  const sp = useSearchParams();
  const [query, setQuery] = useState(sp.get("q") ?? "");
  const [includeDocs, setIncludeDocs] = useState(true);
  const [includeWiki, setIncludeWiki] = useState(true);
  const [activeOnly, setActiveOnly] = useState(true);
  const [project, setProject] = useState(sp.get("project") ?? "");
  const [docTypes, setDocTypes] = useState<string[]>([]);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [documentIds, setDocumentIds] = useState(sp.get("document_ids") ?? "");
  const [k, setK] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const run = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const ids = splitCsv(documentIds);
      const r = await searchApi({
        query: query.trim(),
        k,
        project: project || null,
        doc_types: docTypes.length ? docTypes : undefined,
        disciplines: disciplines.length ? disciplines : undefined,
        document_ids: ids.length ? ids : undefined,
        include_documents: includeDocs,
        include_wiki: includeWiki,
        active_only: activeOnly,
      });
      setResult(r);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader title="Search" subtitle="Hybrid keyword + dense retrieval with reranking." />
      <form onSubmit={run} className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. minimum wall thickness for carbon steel pipe at 10 bar"
            autoFocus
          />
          <Button type="submit" variant="primary" disabled={busy || !query.trim()}>
            {busy ? <Spinner className="border-slate-500 border-t-white" /> : null}
            Search
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <Checkbox label="Documents" checked={includeDocs} onChange={setIncludeDocs} />
          <Checkbox label="Wiki" checked={includeWiki} onChange={setIncludeWiki} />
          <Checkbox label="Active revisions only" checked={activeOnly} onChange={setActiveOnly} />
          <button
            type="button"
            className="ml-auto text-xs text-blue-700 hover:underline"
            onClick={() => setShowFilters((s) => !s)}
          >
            {showFilters ? "Hide filters" : "More filters"}
          </button>
        </div>
        {showFilters && (
          <div className="mt-3 grid gap-3 border-t border-slate-100 pt-3 md:grid-cols-3">
            <Field label="Project">
              <Input value={project} onChange={(e) => setProject(e.target.value)} placeholder="Any" />
            </Field>
            <Field label="Document IDs" hint="Comma-separated UUIDs">
              <Input value={documentIds} onChange={(e) => setDocumentIds(e.target.value)} placeholder="Any" />
            </Field>
            <Field label="Results (k)">
              <Input
                type="number"
                min={1}
                max={100}
                value={k}
                onChange={(e) => setK(Math.max(1, Math.min(100, Number(e.target.value) || 20)))}
              />
            </Field>
            <Field label="Document types" className="md:col-span-3">
              <ChipSelect options={DOC_TYPES} value={docTypes} onChange={setDocTypes} />
            </Field>
            <Field label="Disciplines" className="md:col-span-3">
              <ChipSelect options={DISCIPLINES} value={disciplines} onChange={setDisciplines} />
            </Field>
          </div>
        )}
      </form>

      <div className="mt-4 space-y-3">
        <ErrorBox error={error} />
        {busy && !result && <Loading label="Searching" />}
        {result && (
          <>
            <div className="text-xs text-slate-500">
              {result.hits.length} result{result.hits.length === 1 ? "" : "s"} for{" "}
              <span className="font-medium text-slate-700">“{result.query}”</span>
            </div>
            {result.hits.length === 0 ? (
              <Empty>No matches. Try broader terms or include the wiki.</Empty>
            ) : (
              result.hits.map((h, i) => <HitCard key={h.id} hit={h} query={result.query} index={i + 1} />)
            )}
          </>
        )}
      </div>
    </Page>
  );
}
