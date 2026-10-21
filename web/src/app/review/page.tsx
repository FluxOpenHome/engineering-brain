"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { errorMessage, wiki as wikiApi } from "@/lib/api";
import { fmtDate, pct } from "@/lib/format";
import type { WikiProposalSummary } from "@/lib/types";
import { Badge, Empty, ErrorBox, Loading, Page, PageHeader, Select, Table, Td, Th } from "@/components/ui";

export default function ReviewPage() {
  const [status, setStatus] = useState("open");
  const [items, setItems] = useState<WikiProposalSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItems(null);
    wikiApi
      .proposals(status)
      .then(setItems)
      .catch((e) => setError(errorMessage(e)));
  }, [status]);

  return (
    <Page wide>
      <PageHeader
        title="Review"
        subtitle="Wiki proposals drafted by the system from ingested documents. Nothing is published without acceptance."
        actions={
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36">
            <option value="open">open</option>
            <option value="accepted">accepted</option>
            <option value="rejected">rejected</option>
          </Select>
        }
      />
      <ErrorBox error={error} />
      {items === null && !error ? (
        <Loading />
      ) : items && items.length === 0 ? (
        <Empty>No {status} proposals.</Empty>
      ) : (
        items && (
          <Table>
            <thead>
              <tr>
                <Th>Title</Th>
                <Th>Page</Th>
                <Th>Kind</Th>
                <Th>Confidence</Th>
                <Th>Sources</Th>
                <Th>Created</Th>
                <Th>By</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <Td>
                    <Link href={`/review/${p.id}`} className="font-medium text-slate-900 hover:underline">
                      {p.title}
                    </Link>
                    {p.rationale && <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{p.rationale}</div>}
                  </Td>
                  <Td className="font-mono text-xs">{p.slug}</Td>
                  <Td>
                    <Badge tone={p.kind === "create" ? "green" : "blue"}>{p.kind}</Badge>
                  </Td>
                  <Td>
                    <Confidence value={p.confidence} />
                  </Td>
                  <Td className="tabular-nums">{p.sources?.length ?? 0}</Td>
                  <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(p.created_at)}</Td>
                  <Td className="text-xs text-slate-500">{p.created_by ?? ""}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )
      )}
    </Page>
  );
}

function Confidence({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-xs text-slate-400">–</span>;
  const tone = value >= 0.8 ? "green" : value >= 0.5 ? "amber" : "red";
  return <Badge tone={tone}>{pct(value)}</Badge>;
}
