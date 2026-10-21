// Types mirror the backend contract exactly (see README "Backend contract").

export type UUID = string;

export type DocType =
  | "spec"
  | "datasheet"
  | "standard"
  | "drawing"
  | "report"
  | "procedure"
  | "other";

export const DOC_TYPES: DocType[] = [
  "spec",
  "datasheet",
  "standard",
  "drawing",
  "report",
  "procedure",
  "other",
];

export type Discipline =
  | "fluid"
  | "electrical"
  | "civil"
  | "structural"
  | "mechanical"
  | "chemical"
  | "materials"
  | "ic"
  | "general";

export const DISCIPLINES: Discipline[] = [
  "fluid",
  "electrical",
  "civil",
  "structural",
  "mechanical",
  "chemical",
  "materials",
  "ic",
  "general",
];

export type ParseStatus = "queued" | "running" | "done" | "failed" | string;

// ---------- Documents ----------

export interface DocumentListItem {
  id: UUID;
  doc_number: string | null;
  title: string | null;
  doc_type: string | null;
  discipline: string[] | null;
  project: string | null;
  created_at: string;
  current_revision: string | null;
  parse_status: ParseStatus | null;
  parse_pass: number | null;
  page_count: number | null;
}

export interface DocumentRevision {
  id: UUID;
  revision: string | null;
  status: string | null;
  parse_status: ParseStatus | null;
  parse_pass: number | null;
  page_count: number | null;
  created_at: string;
}

export interface DocumentDetail extends DocumentListItem {
  current_revision_id?: UUID | null;
  revision_status: string | null;
  filename: string | null;
  mime: string | null;
  revisions: DocumentRevision[];
  // Any extra columns from documents.* that the backend returns.
  [key: string]: unknown;
}

export interface UploadResponse {
  document_id: UUID;
  revision_id: UUID;
  duplicate: boolean;
  job_id: string | null;
}

// ---------- Search ----------

export type HitSource = "document" | "wiki";

export interface Hit {
  id: UUID;
  source: HitSource;
  text: string;
  context_prefix: string | null;
  score: number | null;
  rank_keyword: number | null;
  rank_dense: number | null;
  rerank_score: number | null;
  document_id: UUID | null;
  revision_id: UUID | null;
  page_id: UUID | null;
  title: string | null;
  doc_number: string | null;
  revision: string | null;
  section_path: string[] | null;
  clause_id: string | null;
  page_start: number | null;
  page_end: number | null;
  kind: string | null;
}

export interface SearchRequest {
  query: string;
  k?: number;
  document_ids?: UUID[];
  revision_ids?: UUID[];
  project?: string | null;
  doc_types?: string[];
  disciplines?: string[];
  include_documents: boolean;
  include_wiki: boolean;
  active_only: boolean;
}

export interface SearchResponse {
  query: string;
  hits: Hit[];
}

// ---------- Chat ----------

export interface Citation {
  index: number;
  chunk_id: UUID | null;
  source: HitSource | string;
  title: string | null;
  doc_number: string | null;
  revision: string | null;
  clause_id: string | null;
  page_start: number | null;
  page_end: number | null;
  section_path: string[] | null;
  cited_text: string | null;
  document_id: UUID | null;
  page_id: UUID | null;
}

export interface ChatRequest {
  question: string;
  conversation_id?: UUID | null;
  document_ids?: UUID[];
  project?: string | null;
  include_documents: boolean;
  include_wiki: boolean;
  k?: number;
}

export interface Usage {
  [key: string]: number | undefined;
}

export interface ChatResponse {
  conversation_id: UUID;
  answer: string;
  citations: Citation[];
  sources: Hit[];
  usage: Usage;
  model: string;
}

export interface ConversationSummary {
  id: UUID;
  title: string | null;
  created_at: string;
}

export interface ConversationMessage {
  id: UUID;
  role: "user" | "assistant" | string;
  content: string;
  citations: Citation[] | null;
  usage: Usage | null;
  created_at: string;
}

export interface ConversationDetail {
  conversation: ConversationSummary & { scope?: unknown };
  messages: ConversationMessage[];
}

export type ChatStreamEvent =
  | { event: "conversation"; data: { conversation_id: UUID } }
  | { event: "sources"; data: Hit[] }
  | { event: "delta"; data: { text: string } }
  | { event: "done"; data: { citations: Citation[]; usage: Usage; model: string } }
  | { event: "error"; data: { message?: string; detail?: string } }
  | { event: string; data: unknown };

// ---------- Wiki ----------

export interface WikiPageSummary {
  id: UUID;
  slug: string;
  title: string;
  status: string;
  discipline: string | string[] | null;
  tags: string[] | null;
  updated_at: string;
  human_edited: boolean;
}

export interface WikiTreeNode {
  name: string;
  slug?: string;
  children: WikiTreeNode[];
}

export interface WikiSource {
  document_id?: UUID | null;
  revision_id?: UUID | null;
  chunk_id?: UUID | null;
  doc_number?: string | null;
  title?: string | null;
  revision?: string | null;
  page?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  clause_id?: string | null;
  [key: string]: unknown;
}

export interface WikiHistoryEntry {
  sha: string;
  author: string;
  date: string;
  message: string;
}

export interface WikiFrontmatter {
  status?: string;
  discipline?: string | string[];
  tags?: string[];
  human_edited?: boolean;
  [key: string]: unknown;
}

export interface WikiPage {
  id: UUID;
  slug: string;
  title: string;
  status: string;
  frontmatter: WikiFrontmatter;
  content: string;
  sources: WikiSource[];
  history: WikiHistoryEntry[];
}

export interface WikiPagePut {
  title: string;
  content: string;
  discipline?: string | null;
  tags?: string[];
  message?: string;
}

export interface WikiProposalSummary {
  id: UUID;
  slug: string;
  kind: string;
  title: string;
  rationale: string | null;
  confidence: number | null;
  sources: WikiSource[];
  created_at: string;
  created_by: string | null;
  status: string;
}

export interface WikiProposal extends WikiProposalSummary {
  content: string;
  current_content: string | null;
  diff: string | null;
  stale_base: boolean;
}

export interface JobResponse {
  job_id: string;
}

// ---------- Compliance ----------

export interface ComplianceSet {
  id: UUID;
  name: string;
  description: string | null;
  discipline: string | null;
  created_at?: string;
  requirement_count?: number;
  [key: string]: unknown;
}

export interface Requirement {
  id: UUID;
  req_id: string;
  text: string;
  kind: string | null;
  quantity: Quantity | null;
  ears_pattern?: string | null;
}

export interface Quantity {
  value?: number | null;
  min?: number | null;
  max?: number | null;
  unit?: string | null;
  comparator?: string | null;
  [key: string]: unknown;
}

export interface ComplianceSetDetail {
  set: ComplianceSet;
  requirements: Requirement[];
}

export type Verdict =
  | "compliant"
  | "non_compliant"
  | "partial"
  | "insufficient_evidence"
  | "unverified"
  | "not_applicable";

export const VERDICTS: Verdict[] = [
  "compliant",
  "non_compliant",
  "partial",
  "insufficient_evidence",
  "unverified",
  "not_applicable",
];

export type RunStatus = "queued" | "running" | "done" | "failed" | string;

export interface ComplianceRunSummary {
  counts: Partial<Record<Verdict, number>> & Record<string, number>;
  needs_review: number;
  false_compliant_guard: number | boolean;
  unrequested_claims?: UnrequestedClaim[] | number;
}

export interface UnrequestedClaim {
  text?: string;
  quote?: string;
  page?: number | null;
  chunk_id?: UUID | null;
  [key: string]: unknown;
}

export interface ComplianceRun {
  id: UUID;
  set_id: UUID;
  subject_document_id: UUID;
  subject_revision_id: UUID | null;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  summary: ComplianceRunSummary | null;
}

export interface Evidence {
  chunk_id: UUID | null;
  quote: string;
  page: number | null;
  verified: boolean;
}

export interface NumericCheck {
  passed?: boolean | null;
  expected?: string | number | null;
  found?: string | number | null;
  unit?: string | null;
  comparator?: string | null;
  message?: string | null;
  [key: string]: unknown;
}

export interface Finding {
  id: UUID;
  requirement: {
    id: UUID;
    req_id: string;
    text: string;
    kind: string | null;
    quantity: Quantity | null;
  };
  verdict: Verdict | string;
  llm_verdict: Verdict | string | null;
  confidence: number | null;
  evidence: Evidence[];
  numeric_check: NumericCheck | null;
  rationale: string | null;
  needs_review: boolean;
  reviewer_verdict: Verdict | string | null;
  reviewer_note: string | null;
}

export interface ComplianceRunDetail {
  run: ComplianceRun;
  findings: Finding[];
  summary: ComplianceRunSummary;
}

// ---------- Specs ----------

export interface SpecTemplateParameter {
  name: string;
  unit: string | null;
  description: string | null;
  required: boolean;
  interface: boolean;
}

export interface SpecTemplate {
  key: string;
  name: string;
  discipline: string | null;
  standards_refs: string[];
  parameters: SpecTemplateParameter[];
  interface_checklist: string[];
}

export type IssueSeverity = "error" | "warning" | "info" | string;

export interface SpecIssue {
  rule: string;
  severity: IssueSeverity;
  message: string;
}

export interface SpecCheckRequirement {
  text: string;
  issues: SpecIssue[];
  ears_pattern: string | null;
}

export interface SpecCheckResponse {
  requirements: SpecCheckRequirement[];
  summary: Record<string, number | string>;
}

export interface SpecDraftParameter {
  name: string;
  value: string | number | null;
  unit: string | null;
  source_citation: string | Citation | null;
  note: string | null;
}

export interface SpecDraftResponse {
  markdown: string;
  parameters: SpecDraftParameter[];
  issues: SpecIssue[] | SpecCheckRequirement[];
}
