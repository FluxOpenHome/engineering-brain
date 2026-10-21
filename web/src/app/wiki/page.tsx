"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { errorMessage, wiki as wikiApi } from "@/lib/api";
import { fmtDate, slugify } from "@/lib/format";
import type { WikiPageSummary } from "@/lib/types";
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
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";

export default function WikiIndexPage() {
  return (
    <Suspense fallback={<Page><Loading /></Page>}>
      <WikiIndexInner />
    </Suspense>
  );
}

function WikiIndexInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [pages, setPages] = useState<WikiPageSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(sp.get("new") === "1");
  const [newSlug, setNewSlug] = useState("");
  const [newTitle, setNewTitle] = useState("");

  useEffect(() => {
    setShowNew(sp.get("new") === "1");
  }, [sp]);

  useEffect(() => {
    let active = true;
    const t = setTimeout(() => {
      wikiApi
        .pages({ q: q || undefined, status: status || undefined, discipline: discipline || undefined })
        .then((p) => {
          if (active) {
            setPages(p);
            setError(null);
          }
        })
        .catch((e) => active && setError(errorMessage(e)));
    }, 200);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [q, status, discipline]);

  const createPage = (e: React.FormEvent) => {
    e.preventDefault();
    const slug = slugify(newSlug || newTitle);
    if (!slug) return;
    router.push(`/wiki/${slug}?edit=1&title=${encodeURIComponent(newTitle || slug)}`);
  };

  return (
    <Page>
      <PageHeader
        title="Wiki"
        subtitle="Engineering knowledge drafted from documents and reviewed by humans."
        actions={
          <>
            <Button onClick={() => setShowNew((s) => !s)} variant="primary">
              New page
            </Button>
            <Link href="/review" className="text-sm text-blue-700 hover:underline">
              Open proposals
            </Link>
          </>
        }
      />

      {showNew && (
        <Card title="Create a page" className="mb-4">
          <form onSubmit={createPage} className="grid gap-3 md:grid-cols-3">
            <Field label="Title">
              <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Centrifugal pumps" />
            </Field>
            <Field label="Slug" hint={`Will be /wiki/${slugify(newSlug || newTitle) || "…"}`}>
              <Input
                value={newSlug}
                onChange={(e) => setNewSlug(e.target.value)}
                placeholder="mechanical/pumps/centrifugal"
              />
            </Field>
            <div className="flex items-end">
              <Button type="submit" variant="primary" disabled={!slugify(newSlug || newTitle)}>
                Open editor
              </Button>
            </div>
          </form>
        </Card>
      )}

      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Field label="Search" className="w-72">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Title or content…" />
        </Field>
        <Field label="Status" className="w-40">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any</option>
            <option value="published">published</option>
            <option value="draft">draft</option>
            <option value="stale">stale</option>
            <option value="archived">archived</option>
          </Select>
        </Field>
        <Field label="Discipline" className="w-40">
          <Input value={discipline} onChange={(e) => setDiscipline(e.target.value)} placeholder="Any" />
        </Field>
      </div>

      <ErrorBox error={error} />
      {pages === null && !error ? (
        <Loading />
      ) : pages && pages.length === 0 ? (
        <Empty>No wiki pages match.</Empty>
      ) : (
        pages && (
          <Table>
            <thead>
              <tr>
                <Th>Title</Th>
                <Th>Slug</Th>
                <Th>Status</Th>
                <Th>Discipline</Th>
                <Th>Tags</Th>
                <Th>Edited</Th>
                <Th>Updated</Th>
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <Td>
                    <Link href={`/wiki/${p.slug}`} className="font-medium text-slate-900 hover:underline">
                      {p.title}
                    </Link>
                  </Td>
                  <Td className="font-mono text-xs text-slate-500">{p.slug}</Td>
                  <Td>
                    <StatusBadge status={p.status} />
                  </Td>
                  <Td>
                    {(Array.isArray(p.discipline) ? p.discipline : p.discipline ? [p.discipline] : []).map((d) => (
                      <Badge key={d} tone="blue" className="mr-1">
                        {d}
                      </Badge>
                    ))}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {(p.tags ?? []).map((t) => (
                        <Badge key={t}>{t}</Badge>
                      ))}
                    </div>
                  </Td>
                  <Td>{p.human_edited ? <Badge tone="green">human</Badge> : <Badge tone="grey">agent</Badge>}</Td>
                  <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(p.updated_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )
      )}
    </Page>
  );
}
