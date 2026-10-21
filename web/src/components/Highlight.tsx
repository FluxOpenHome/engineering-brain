"use client";

import { useMemo } from "react";

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Wraps query terms (3+ chars) in <mark>. */
export function Highlight({ text, query }: { text: string; query: string }) {
  const parts = useMemo(() => {
    const terms = Array.from(
      new Set(
        query
          .toLowerCase()
          .split(/[^\p{L}\p{N}.-]+/u)
          .filter((t) => t.length >= 3),
      ),
    );
    if (terms.length === 0) return [{ t: text, m: false }];
    const re = new RegExp(`(${terms.map(escapeRe).join("|")})`, "gi");
    return text.split(re).map((t) => ({ t, m: terms.includes(t.toLowerCase()) }));
  }, [text, query]);
  return (
    <>
      {parts.map((p, i) => (p.m ? <mark key={i}>{p.t}</mark> : <span key={i}>{p.t}</span>))}
    </>
  );
}
