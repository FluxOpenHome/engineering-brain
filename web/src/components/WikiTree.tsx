"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { errorMessage, wiki as wikiApi } from "@/lib/api";
import type { WikiTreeNode } from "@/lib/types";
import { Loading } from "./ui";

export function WikiTree() {
  const [tree, setTree] = useState<WikiTreeNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    wikiApi.tree().then(setTree).catch((e) => setError(errorMessage(e)));
  }, [pathname]);

  const current = decodeURIComponent(pathname.replace(/^\/wiki\/?/, ""));

  return (
    <aside className="w-64 shrink-0 border-r border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5">
        <Link href="/wiki" className="text-sm font-semibold hover:underline">
          Wiki
        </Link>
        <Link
          href="/wiki?new=1"
          className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white hover:bg-slate-700"
        >
          New page
        </Link>
      </div>
      <div className="max-h-[calc(100vh-3rem)] overflow-y-auto p-2 text-sm">
        {error && <div className="px-1 text-xs text-red-600">{error}</div>}
        {!tree && !error && <Loading />}
        {tree && (tree.children?.length ? (
          <ul>
            {tree.children.map((n, i) => (
              <TreeNode key={`${n.slug ?? n.name}-${i}`} node={n} depth={0} current={current} />
            ))}
          </ul>
        ) : (
          <div className="px-2 py-3 text-xs text-slate-400">No pages yet.</div>
        ))}
      </div>
    </aside>
  );
}

function TreeNode({ node, depth, current }: { node: WikiTreeNode; depth: number; current: string }) {
  const hasChildren = node.children && node.children.length > 0;
  const isCurrent = node.slug != null && node.slug === current;
  const containsCurrent = node.slug != null && current.startsWith(node.slug + "/");
  const [open, setOpen] = useState(depth < 1 || containsCurrent);
  useEffect(() => {
    if (containsCurrent) setOpen(true);
  }, [containsCurrent]);
  return (
    <li>
      <div
        className={`flex items-center gap-1 rounded px-1 py-0.5 ${
          isCurrent ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
        }`}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className={`w-4 text-center text-xs ${isCurrent ? "text-slate-300" : "text-slate-400"}`}
            aria-label={open ? "collapse" : "expand"}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-4" />
        )}
        {node.slug ? (
          <Link href={`/wiki/${node.slug}`} className="flex-1 truncate py-0.5" title={node.slug}>
            {node.name}
          </Link>
        ) : (
          <span className="flex-1 truncate py-0.5 font-medium">{node.name}</span>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((c, i) => (
            <TreeNode key={`${c.slug ?? c.name}-${i}`} node={c} depth={depth + 1} current={current} />
          ))}
        </ul>
      )}
    </li>
  );
}
