// Typed client for the PaperLens FastAPI backend. Vite proxies /api to http://127.0.0.1:8000 in development.

export type Verdict = 'Use as proposed' | 'Use with adaptations' | 'Do not use' | 'Need more evidence';
export const VERDICTS: Verdict[] = ['Use as proposed', 'Use with adaptations', 'Do not use', 'Need more evidence'];

export type PaperStatus = 'queued' | 'parsing' | 'indexing' | 'summarizing' | 'ready' | 'failed';
export type Paper = {
  paper_id: string;
  filename: string;
  title: string;
  status: PaperStatus;
  error: string | null;
  failed_stage: string | null;
  page_count?: number;
  chunk_count?: number;
  page_labels_differ?: boolean;
};

export type Source = {
  ref_id: string;
  kind: 'paper' | 'overview' | 'unknown';
  page: number | null;
  page_label: string | null;
  pages?: number[];
  text: string | null;
  verified: boolean;
  /** Verified sentences copied from this passage (prompt p3+); highlighted on the PDF page. */
  quotes?: string[];
};
export type SectionKind = 'paper' | 'explanation' | 'example' | 'inference' | 'research_use' | 'limitation';
export type AnswerSection = { title: string; kind: SectionKind; text: string; refs: string[] };
export type SystemSuggestion = { verdict: Verdict; reason: string };
export type TurnMode = 'chat' | 'critical_review' | 'judgment_feedback';

export type UserMessage = { id: string; role: 'user'; mode: TurnMode; text: string; created_at: string };
export type AssistantMessage = {
  id: string;
  role: 'assistant';
  mode: TurnMode;
  created_at: string;
  short_answer: string;
  short_answer_refs: string[];
  sections: AnswerSection[];
  sources: Source[];
  evidence_status: 'sufficient' | 'partial' | 'insufficient';
  has_verified_paper_source: boolean;
  clarifying_question: string;
  follow_up_suggestions: string[];
  system_suggestion: SystemSuggestion | null;
  retrieval_query: string;
  pipeline_version: string;
};
export type Message = UserMessage | AssistantMessage;

export type Judgment = { verdict: Verdict; rationale: string; submitted_at: string };
export type Note = {
  selected_idea: string;
  evidence: { point: string; sources: Source[] }[];
  research_use: string;
  adaptations_and_uncertainties: string;
  next_actions: string[];
  learner_judgment: Judgment | null;
  system_suggestion: SystemSuggestion | null;
  generated_at: string;
  edited_by_learner: boolean;
};
export type Session = {
  session_id: string;
  paper_id: string;
  paper_title: string;
  reading_goal: string;
  research_context: string;
  language: string;
  current_concept: string;
  messages: Message[];
  system_suggestion: SystemSuggestion | null;
  judgment: Judgment | null;
  note: Note | null;
};
export type SessionSummary = {
  session_id: string; paper_id: string; paper_title: string; reading_goal: string; updated_at: string; first_question: string;
};
export type TurnResult = { ok: true; message: AssistantMessage; event_id: string } | { ok: false; error: string; event_id: string };

/** `code: 'unreachable'` lets the UI show its own translated message. */
export class ApiError extends Error {
  constructor(message: string, readonly code?: 'unreachable') { super(message); }
}
const unreachable = () => new ApiError('Cannot reach the PaperLens backend. Start it with `npm run backend`, then retry.', 'unreachable');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw unreachable();
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // No JSON body on a 5xx: the dev-server proxy could not reach FastAPI.
    if (body === null && response.status >= 500) throw unreachable();
    const detail = body?.detail;
    throw new ApiError(typeof detail === 'string' ? detail : `Request failed (${response.status}).`);
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
});

export const api = {
  uploadPaper(file: File) {
    const form = new FormData();
    form.append('file', file);
    return request<Paper>('/papers', { method: 'POST', body: form });
  },
  uploadPaperUrl: (url: string) => request<Paper>('/papers/from-url', json('POST', { url })),
  paper: (paperId: string) => request<Paper>(`/papers/${paperId}`),
  retryPaper: (paperId: string) => request<Paper>(`/papers/${paperId}/retry`, { method: 'POST' }),
  pdfUrl: (paperId: string) => `/api/papers/${paperId}/pdf`,
  sessions: () => request<SessionSummary[]>('/sessions'),
  session: (sessionId: string) => request<Session>(`/sessions/${sessionId}`),
  createSession: (data: { paper_id: string; reading_goal: string; research_context: string; language: string }) =>
    request<Session>('/sessions', json('POST', data)),
  updateSession: (sessionId: string, data: Partial<Pick<Session, 'reading_goal' | 'research_context' | 'language'>>) =>
    request<Session>(`/sessions/${sessionId}`, json('PATCH', data)),
  sendMessage: (sessionId: string, message: string) => request<TurnResult>(`/sessions/${sessionId}/messages`, json('POST', { message })),
  criticalReview: (sessionId: string) => request<TurnResult>(`/sessions/${sessionId}/critical-review`, { method: 'POST' }),
  submitJudgment: (sessionId: string, verdict: Verdict, rationale: string) =>
    request<TurnResult & { judgment?: Judgment }>(`/sessions/${sessionId}/judgment`, json('POST', { verdict, rationale })),
  generateNote: (sessionId: string) =>
    request<{ ok: true; note: Note } | { ok: false; error: string }>(`/sessions/${sessionId}/note`, { method: 'POST' }),
  saveNote: (sessionId: string, fields: Record<string, unknown>) => request<Note>(`/sessions/${sessionId}/note`, json('PUT', fields)),
  deleteSession: (sessionId: string) => request<{ ok: true }>(`/sessions/${sessionId}`, { method: 'DELETE' }),
  exportUrl: (sessionId: string) => `/api/sessions/${sessionId}/export`,
  noteMarkdownUrl: (sessionId: string) => `/api/sessions/${sessionId}/note.md`,
};

/** Start a browser download of a backend URL (the server sets Content-Disposition). */
export function download(url: string, filename: string) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
}
