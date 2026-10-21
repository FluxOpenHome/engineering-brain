"use client";

import { Markdown } from "@tiptap/markdown";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect } from "react";

/**
 * Tiptap v3 editor that loads and exposes markdown. Call `editor.getMarkdown()`
 * through `onReady` to read the current content.
 */
export function WikiEditor({
  initialMarkdown,
  onReady,
}: {
  initialMarkdown: string;
  onReady?: (editor: Editor) => void;
}) {
  const editor = useEditor({
    extensions: [StarterKit.configure({ link: { openOnClick: false } }), Markdown],
    content: initialMarkdown,
    contentType: "markdown",
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: "tiptap prose-eb px-4 py-3",
      },
    },
  });

  useEffect(() => {
    if (editor && onReady) onReady(editor);
  }, [editor, onReady]);

  if (!editor) return <div className="p-4 text-sm text-slate-400">Loading editor…</div>;

  return (
    <div className="rounded-lg border border-slate-300 bg-white">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} />
    </div>
  );
}

function Toolbar({ editor }: { editor: Editor }) {
  const btn = (label: string, action: () => void, active = false, title?: string) => (
    <button
      type="button"
      title={title ?? label}
      onMouseDown={(e) => {
        e.preventDefault();
        action();
      }}
      className={`rounded px-2 py-1 text-xs font-medium ${
        active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
      }`}
    >
      {label}
    </button>
  );
  const c = editor.chain().focus();
  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-slate-200 px-2 py-1">
      {btn("H1", () => c.toggleHeading({ level: 1 }).run(), editor.isActive("heading", { level: 1 }))}
      {btn("H2", () => c.toggleHeading({ level: 2 }).run(), editor.isActive("heading", { level: 2 }))}
      {btn("H3", () => c.toggleHeading({ level: 3 }).run(), editor.isActive("heading", { level: 3 }))}
      <span className="mx-1 h-4 w-px bg-slate-200" />
      {btn("B", () => c.toggleBold().run(), editor.isActive("bold"), "Bold")}
      {btn("I", () => c.toggleItalic().run(), editor.isActive("italic"), "Italic")}
      {btn("S", () => c.toggleStrike().run(), editor.isActive("strike"), "Strikethrough")}
      {btn("Code", () => c.toggleCode().run(), editor.isActive("code"))}
      <span className="mx-1 h-4 w-px bg-slate-200" />
      {btn("• List", () => c.toggleBulletList().run(), editor.isActive("bulletList"))}
      {btn("1. List", () => c.toggleOrderedList().run(), editor.isActive("orderedList"))}
      {btn("Quote", () => c.toggleBlockquote().run(), editor.isActive("blockquote"))}
      {btn("Code block", () => c.toggleCodeBlock().run(), editor.isActive("codeBlock"))}
      {btn("Rule", () => c.setHorizontalRule().run())}
      <span className="mx-1 h-4 w-px bg-slate-200" />
      {btn("Link", () => {
        const prev = editor.getAttributes("link").href as string | undefined;
        const url = window.prompt("URL", prev ?? "https://");
        if (url === null) return;
        if (url === "") {
          editor.chain().focus().extendMarkRange("link").unsetLink().run();
          return;
        }
        editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
      }, editor.isActive("link"))}
      <span className="mx-1 h-4 w-px bg-slate-200" />
      {btn("Undo", () => c.undo().run())}
      {btn("Redo", () => c.redo().run())}
    </div>
  );
}
