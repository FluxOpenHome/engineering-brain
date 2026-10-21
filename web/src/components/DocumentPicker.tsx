"use client";

import { useEffect, useMemo, useState } from "react";
import { documents as docsApi, errorMessage } from "@/lib/api";
import type { DocumentListItem } from "@/lib/types";
import { Input, Select } from "./ui";

/** Search-as-you-type picker over GET /documents; returns a document id. */
export function DocumentPicker({
  value,
  onChange,
  placeholder = "Filter documents…",
  disabled,
}: {
  value: string;
  onChange: (id: string, doc: DocumentListItem | null) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [q, setQ] = useState("");
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const t = setTimeout(() => {
      docsApi
        .list({ q: q || undefined, limit: 100 })
        .then((d) => {
          if (active) {
            setDocs(d);
            setError(null);
          }
        })
        .catch((e) => active && setError(errorMessage(e)));
    }, 200);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [q]);

  const byId = useMemo(() => new Map(docs.map((d) => [d.id, d])), [docs]);

  return (
    <div className="flex flex-col gap-1.5">
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
      <Select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value, byId.get(e.target.value) ?? null)}
      >
        <option value="">Select a document…</option>
        {docs.map((d) => (
          <option key={d.id} value={d.id}>
            {[d.doc_number, d.title].filter(Boolean).join(" — ") || d.id}
            {d.current_revision ? ` (Rev ${d.current_revision})` : ""}
          </option>
        ))}
      </Select>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
