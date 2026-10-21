"use client";

import Link from "next/link";
import type { Hit } from "@/lib/types";
import { fmtPages } from "@/lib/format";
import { Badge } from "./ui";
import { Highlight } from "./Highlight";

export function HitCard({
  hit,
  query,
  index,
  highlighted = false,
  compact = false,
  id,
}: {
  hit: Hit;
  query?: string;
  index?: number;
  highlighted?: boolean;
  compact?: boolean;
  id?: string;
}) {
  const pages = fmtPages(hit.page_start, hit.page_end);
  const titleNode = (
    <span className="font-medium text-slate-900">
      {hit.title || hit.doc_number || (hit.source === "wiki" ? "Wiki page" : "Document")}
    </span>
  );
  return (
    <article
      id={id}
      className={`rounded-lg border bg-white p-3 transition-shadow ${
        highlighted ? "border-amber-400 shadow-[0_0_0_3px_rgba(251,191,36,0.35)]" : "border-slate-200"
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {index != null && (
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-900 text-[11px] font-semibold text-white">
            {index}
          </span>
        )}
        <Badge tone={hit.source === "wiki" ? "purple" : "blue"}>{hit.source}</Badge>
        {hit.document_id ? (
          <Link href={`/documents/${hit.document_id}`} className="hover:underline">
            {titleNode}
          </Link>
        ) : (
          titleNode
        )}
        {hit.doc_number && <span className="font-mono text-xs text-slate-600">{hit.doc_number}</span>}
        {hit.revision && <span className="text-xs text-slate-500">Rev {hit.revision}</span>}
        {hit.clause_id && <Badge tone="slate">cl. {hit.clause_id}</Badge>}
        {pages && <span className="text-xs text-slate-500">{pages}</span>}
        {hit.kind && hit.kind !== "text" && <Badge tone="grey">{hit.kind}</Badge>}
      </div>
      {hit.section_path && hit.section_path.length > 0 && (
        <div className="mt-1 truncate text-xs text-slate-500" title={hit.section_path.join(" › ")}>
          {hit.section_path.join(" › ")}
        </div>
      )}
      <p
        className={`mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-800 ${
          compact ? "line-clamp-6" : ""
        }`}
      >
        {query ? <Highlight text={hit.text} query={query} /> : hit.text}
      </p>
      {!compact && (
        <div className="mt-2 flex flex-wrap gap-3 font-mono text-[11px] text-slate-400">
          {hit.score != null && <span>score {hit.score.toFixed(4)}</span>}
          {hit.rerank_score != null && <span>rerank {hit.rerank_score.toFixed(3)}</span>}
          {hit.rank_keyword != null && <span>kw #{hit.rank_keyword}</span>}
          {hit.rank_dense != null && <span>dense #{hit.rank_dense}</span>}
        </div>
      )}
    </article>
  );
}
