# ADR-0002: Markdown + frontmatter in git is the canonical wiki store, with a web editor on top

Status: accepted, 2026-10-21

## Context
The user previously used Obsidian as a structured markdown database. The research found no
file-based tool has become a multi-user system of record (Obsidian has no headless API or
permissions; Logseq DB is beta; SiYuan is single-writer), while every working LLM-wiki
implementation operates on plain markdown files with frontmatter and git history.

## Decision
The wiki is a git repository of `<slug>.md` files with YAML frontmatter (`status`, `sources`,
`generated_by`, `reviewed_by`, `human_edited`, ...). Agents write proposals into the database, never
files; a reviewer accepts a proposal, which commits the file and publishes the page. Humans edit
through a Tiptap/Hocuspocus web editor that commits on save. The database holds an index of pages
and chunks; only `published` pages are indexed for chat. Obsidian remains an optional client on the
same repository.

## Consequences
- Full history and diffs for free; agents can read and lint the whole wiki with file tools.
- Review gate is mandatory for machine-written content (Wikipedia 2026 precedent).
- ADR-0005 decides between building the editor (Tiptap) and adopting Outline.
