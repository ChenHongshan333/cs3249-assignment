// Research-use note: generated from the real session, editable by the learner.
// The learner's verdict/rationale come verbatim from what they typed; PaperLens's suggestion is shown separately.
import { useEffect, useState } from 'react';
import { ChevronLeft, LoaderCircle, NotebookPen } from 'lucide-react';
import { pageText, type Note, type Session } from '../api';
import type { SourceFocus } from './PaperPane';

export function SessionNotes({ session, busy, error, onGenerate, onSave, onBack, onSource }: {
  session: Session | null; busy: boolean; error: string;
  onGenerate: () => void; onSave: (fields: Record<string, unknown>) => void; onBack: () => void; onSource: (s: SourceFocus) => void;
}) {
  const note = session?.note ?? null;
  const [draft, setDraft] = useState<Note | null>(note);
  useEffect(() => setDraft(note), [note]);
  const hasExchange = !!session?.messages.some((m) => m.role === 'assistant');

  const header = <>
    <button className="back-link" onClick={onBack}><ChevronLeft /> Back to conversation</button>
    <div className="notes-heading"><div><span>RESEARCH-USE NOTE</span><h1>{draft?.selected_idea ? 'Your note' : 'No note yet'}</h1></div><NotebookPen /></div>
    <p className="notes-intro">A decision-focused record of the selected idea, its evidence, possible use and unresolved uncertainty — drafted from this session and editable by you.</p>
    <div className="note-context">
      <small>READING GOAL</small><p>{session?.reading_goal || 'No reading goal selected'}</p>
      <small>MY RESEARCH</small><p>{session?.research_context || 'Not provided'}</p>
    </div>
  </>;

  if (!draft) {
    return <div className="notes-page">{header}
      <div className="note-empty">
        {error && <p className="inline-error" role="alert">{error}</p>}
        {hasExchange
          ? <button className="primary-button" onClick={onGenerate} disabled={busy}>
            {busy ? <><LoaderCircle className="spin" /> Drafting from this session…</> : 'Draft a note from this session'}</button>
          : <p className="muted-text">Ask PaperLens at least one question about the paper first.</p>}
      </div>
    </div>;
  }

  const set = (patch: Partial<Note>) => setDraft({ ...draft, ...patch });
  const judgment = draft.learner_judgment;
  return <div className="notes-page">{header}
    <h2>Selected idea</h2>
    <textarea className="note-edit selected-idea" value={draft.selected_idea} onChange={(e) => set({ selected_idea: e.target.value })} rows={2} />
    <h2>My judgment</h2>
    <div className="note-context">
      <small>MY FINAL JUDGMENT</small>
      <p className={judgment ? 'judgment-recorded' : ''}>{judgment?.verdict || 'Not decided yet — record your decision after the critical review.'}</p>
      <small>MY REASON</small>
      {judgment
        ? <textarea className="note-edit" value={judgment.rationale} rows={2}
          onChange={(e) => set({ learner_judgment: { ...judgment, rationale: e.target.value } })} />
        : <p>—</p>}
      <small>PAPERLENS SUGGESTED</small>
      <p className="muted-text">{draft.system_suggestion ? `${draft.system_suggestion.verdict} — ${draft.system_suggestion.reason}` : 'No critical review in this session.'}</p>
    </div>
    <h2>Evidence and research use</h2>
    <div className="research-note-grid">
      <article><small>Supporting evidence</small>
        {draft.evidence.length ? draft.evidence.map((item, index) => <div key={index} className="note-evidence">
          <textarea className="note-edit" value={item.point} rows={3}
            onChange={(e) => set({ evidence: draft.evidence.map((ev, i) => i === index ? { ...ev, point: e.target.value } : ev) })} />
          <span className="ref-chips">{item.sources.map((s) => <button key={s.ref_id} className="ref-chip wide"
            onClick={() => onSource({ ...s, label: 'Note evidence' })}>{pageText(s)}</button>)}</span>
        </div>) : <p className="muted-text">No cited evidence in this session.</p>}
      </article>
      <article><small>Possible use in my research</small>
        <textarea className="note-edit" value={draft.research_use} rows={6} onChange={(e) => set({ research_use: e.target.value })} /></article>
      <article><small>Required adaptations & uncertainties</small>
        <textarea className="note-edit" value={draft.adaptations_and_uncertainties} rows={6}
          onChange={(e) => set({ adaptations_and_uncertainties: e.target.value })} /></article>
      <article><small>Next actions</small>
        <textarea className="note-edit" value={draft.next_actions.join('\n')} rows={4}
          onChange={(e) => set({ next_actions: e.target.value.split('\n') })} /></article>
    </div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="form-actions note-actions">
      <span className="muted-text">{draft.edited_by_learner ? 'Edited by you' : 'Drafted by PaperLens from this session'}</span>
      <button className="text-button" onClick={onGenerate} disabled={busy}>Re-draft from session</button>
      <button className="primary-button" disabled={busy} onClick={() => onSave({
        selected_idea: draft.selected_idea,
        research_use: draft.research_use,
        adaptations_and_uncertainties: draft.adaptations_and_uncertainties,
        next_actions: draft.next_actions,
        evidence_points: draft.evidence.map((e) => e.point),
        rationale: draft.learner_judgment?.rationale,
      })}>Save note</button>
    </div>
  </div>;
}
