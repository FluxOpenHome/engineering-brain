"use client";

import type { Editor } from "@tiptap/react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, errorMessage, wiki as wikiApi } from "@/lib/api";
import { fmtDate, splitCsv } from "@/lib/format";
import type { WikiPage } from "@/lib/types";
import { Markdown } from "@/components/Markdown";
import { WikiEditor } from "@/components/WikiEditor";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  Field,
  Input,
  Loading,
  Notice,
  Page,
  PageHeader,
  Spinner,
  StatusBadge,
} from "@/components/ui";

export default function WikiSlugPage() {
  return (
    <Suspense fallback={<Page><Loading /></Page>}>
      <WikiSlugInner />
    </Suspense>
  );
}

function WikiSlugInner() {
  const params = useParams<{ slug: string[] }>();
  const slug = (params.slug ?? []).map((s) => decodeURIComponent(s)).join("/");
  const sp = useSearchParams();
  const router = useRouter();

  const [page, setPage] = useState<WikiPage | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(sp.get("edit") === "1");

  const load = useCallback(async () => {
    setLoading(true);
    setNotFound(false);
    try {
      const p = await wikiApi.page(slug);
      setPage(p);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setNotFound(true);
        setPage(null);
        setEditing(true);
      } else {
        setError(errorMessage(e));
      }
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !page && !notFound) return <Page><Loading /></Page>;
  if (error && !page) return <Page><ErrorBox error={error} /></Page>;

  if (editing) {
    return (
      <EditView
        slug={slug}
        page={page}
        defaultTitle={sp.get("title") ?? ""}
        onCancel={() => {
          if (notFound) router.push("/wiki");
          else setEditing(false);
        }}
        onSaved={(p) => {
          setPage(p);
          setNotFound(false);
          setEditing(false);
          router.replace(`/wiki/${p.slug}`);
        }}
      />
    );
  }

  if (!page) return null;
  const fm = page.frontmatter ?? {};
  const disciplines = Array.isArray(fm.discipline) ? fm.discipline : fm.discipline ? [fm.discipline] : [];

  const archive = async () => {
    if (!confirm(`Archive "${page.title}"?`)) return;
    try {
      await wikiApi.archive(slug);
      router.push("/wiki");
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Page wide>
      <div className="mb-2 text-xs text-slate-500">
        <Link href="/wiki" className="hover:underline">
          Wiki
        </Link>{" "}
        / <span className="font-mono">{page.slug}</span>
      </div>
      <PageHeader
        title={page.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={page.status ?? fm.status} />
            {disciplines.map((d) => (
              <Badge key={d} tone="blue">
                {d}
              </Badge>
            ))}
            {(fm.tags ?? []).map((t) => (
              <Badge key={t}>{t}</Badge>
            ))}
            {fm.human_edited ? <Badge tone="green">human edited</Badge> : <Badge tone="grey">agent drafted</Badge>}
          </span>
        }
        actions={
          <>
            <Button variant="primary" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button variant="danger" onClick={archive}>
              Archive
            </Button>
          </>
        }
      />
      <ErrorBox error={error} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <Card>
          <Markdown>{page.content}</Markdown>
        </Card>
        <div className="space-y-4">
          <Card title={`Sources (${page.sources?.length ?? 0})`}>
            {!page.sources || page.sources.length === 0 ? (
              <div className="text-xs text-slate-400">No cited sources.</div>
            ) : (
              <ul className="space-y-2 text-xs">
                {page.sources.map((s, i) => {
                  const label = [s.doc_number, s.title].filter(Boolean).join(" — ") || s.document_id || "source";
                  const pg = s.page ?? s.page_start;
                  return (
                    <li key={i} className="rounded border border-slate-100 p-2">
                      {s.document_id ? (
                        <Link href={`/documents/${s.document_id}`} className="font-medium text-blue-700 hover:underline">
                          {label}
                        </Link>
                      ) : (
                        <span className="font-medium">{label}</span>
                      )}
                      <div className="mt-0.5 text-slate-500">
                        {s.revision && <span className="mr-2">Rev {s.revision}</span>}
                        {s.clause_id && <span className="mr-2">cl. {s.clause_id}</span>}
                        {pg != null && <span>p.{pg}</span>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <Card title={`History (${page.history?.length ?? 0})`}>
            {!page.history || page.history.length === 0 ? (
              <div className="text-xs text-slate-400">No commits.</div>
            ) : (
              <ul className="space-y-2 text-xs">
                {page.history.map((h) => (
                  <li key={h.sha} className="border-l-2 border-slate-200 pl-2">
                    <div className="font-medium text-slate-800">{h.message}</div>
                    <div className="text-slate-500">
                      <span className="font-mono">{h.sha.slice(0, 7)}</span> · {h.author} · {fmtDate(h.date)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </Page>
  );
}

function EditView({
  slug,
  page,
  defaultTitle,
  onCancel,
  onSaved,
}: {
  slug: string;
  page: WikiPage | null;
  defaultTitle: string;
  onCancel: () => void;
  onSaved: (p: WikiPage) => void;
}) {
  const fm = page?.frontmatter ?? {};
  const [title, setTitle] = useState(page?.title ?? defaultTitle ?? "");
  const [discipline, setDiscipline] = useState(
    Array.isArray(fm.discipline) ? fm.discipline.join(", ") : (fm.discipline ?? ""),
  );
  const [tags, setTags] = useState((fm.tags ?? []).join(", "));
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editorRef = useRef<Editor | null>(null);
  const onReady = useCallback((e: Editor) => {
    editorRef.current = e;
  }, []);

  const save = async () => {
    const ed = editorRef.current;
    if (!ed) return;
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const content = ed.getMarkdown();
      const disc = discipline.trim();
      const saved = await wikiApi.put(slug, {
        title: title.trim(),
        content,
        discipline: disc ? disc : undefined,
        tags: splitCsv(tags),
        message: message.trim() || (page ? `Edit ${slug}` : `Create ${slug}`),
      });
      onSaved(saved);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page wide>
      <div className="mb-2 text-xs text-slate-500">
        <Link href="/wiki" className="hover:underline">
          Wiki
        </Link>{" "}
        / <span className="font-mono">{slug}</span> / {page ? "edit" : "new"}
      </div>
      <PageHeader
        title={page ? `Editing: ${page.title}` : "New page"}
        subtitle={page ? "Edits commit directly to the wiki repository and publish immediately." : `Creating /wiki/${slug}`}
        actions={
          <>
            <Button onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
            <Button variant="primary" onClick={save} disabled={saving}>
              {saving && <Spinner className="border-slate-500 border-t-white" />}
              Save
            </Button>
          </>
        }
      />
      {!page && <div className="mb-3"><Notice tone="blue">This page does not exist yet; saving will create it.</Notice></div>}
      <div className="mb-3 grid gap-3 md:grid-cols-4">
        <Field label="Title">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Discipline">
          <Input value={discipline} onChange={(e) => setDiscipline(e.target.value)} placeholder="mechanical" />
        </Field>
        <Field label="Tags" hint="Comma-separated">
          <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="pumps, api-610" />
        </Field>
        <Field label="Commit message">
          <Input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="What changed and why" />
        </Field>
      </div>
      <ErrorBox error={error} />
      <div className="mt-3">
        <WikiEditor initialMarkdown={page?.content ?? `# ${title || slug}\n\n`} onReady={onReady} />
      </div>
    </Page>
  );
}
