// Research-use note: generated from the real session, editable by the learner.
// The learner's verdict/rationale come verbatim from what they typed; PaperLens's suggestion is shown separately.
import { useEffect, useState } from 'react';
import { ChevronLeft, Download, LoaderCircle, NotebookPen } from 'lucide-react';
import type { Note, Session } from '../api';
import { useT } from '../i18n';
import type { SourceFocus } from './PaperPane';

export function SessionNotes({ session, busy, error, onGenerate, onSave, onDownload, onBack, onSource }: {
  session: Session | null; busy: boolean; error: string;
  onGenerate: () => void; onSave: (fields: Record<string, unknown>) => Promise<boolean>; onDownload: () => void;
  onBack: () => void; onSource: (s: SourceFocus) => void;
}) {
  const t = useT();
  const note = session?.note ?? null;
  const [draft, setDraft] = useState<Note | null>(note);
  useEffect(() => setDraft(note), [note]);
  const hasExchange = !!session?.messages.some((m) => m.role === 'assistant');
  const goal = session?.reading_goal ?? '';

  const header = <>
    <button className="back-link" onClick={onBack}><ChevronLeft /> {t.backToConversation}</button>
    <div className="notes-heading"><div><span>{t.noteHeading}</span><h1>{draft?.selected_idea ? t.yourNote : t.noNoteYet}</h1></div><NotebookPen /></div>
    <p className="notes-intro">{t.notesIntro}</p>
    <div className="note-context">
      <small>{t.readingGoal}</small><p>{goal ? t.goals[goal] ?? goal : t.noGoal}</p>
      <small>{t.myResearch}</small><p>{session?.research_context || t.notProvided}</p>
    </div>
  </>;

  if (!draft) {
    return <div className="notes-page">{header}
      <div className="note-empty">
        {error && <p className="inline-error" role="alert">{error}</p>}
        {hasExchange
          ? <button className="primary-button" onClick={onGenerate} disabled={busy}>
            {busy ? <><LoaderCircle className="spin" /> {t.drafting}</> : t.draftNote}</button>
          : <p className="muted-text">{t.askFirst}</p>}
      </div>
    </div>;
  }

  const set = (patch: Partial<Note>) => setDraft({ ...draft, ...patch });
  const judgment = draft.learner_judgment;
  const unsaved = JSON.stringify(draft) !== JSON.stringify(note);
  const fields = () => ({
    selected_idea: draft.selected_idea,
    research_use: draft.research_use,
    adaptations_and_uncertainties: draft.adaptations_and_uncertainties,
    next_actions: draft.next_actions,
    evidence_points: draft.evidence.map((e) => e.point),
    rationale: draft.learner_judgment?.rationale,
  });
  // The .md file is built by the backend from the saved note, so unsaved edits are saved first.
  const download = async () => { if (!unsaved || await onSave(fields())) onDownload(); };
  const suggestion = draft.system_suggestion;
  return <div className="notes-page">{header}
    <h2>{t.selectedIdea}</h2>
    <textarea className="note-edit selected-idea" value={draft.selected_idea} onChange={(e) => set({ selected_idea: e.target.value })} rows={2} />
    <h2>{t.myJudgment}</h2>
    <div className="note-context">
      <small>{t.myFinalJudgment}</small>
      <p className={judgment ? 'judgment-recorded' : ''}>{judgment ? t.verdicts[judgment.verdict] : t.notDecided}</p>
      <small>{t.myReason}</small>
      {judgment
        ? <textarea className="note-edit" value={judgment.rationale} rows={2}
          onChange={(e) => set({ learner_judgment: { ...judgment, rationale: e.target.value } })} />
        : <p>—</p>}
      <small>{t.paperlensSuggested}</small>
      <p className="muted-text">{suggestion ? `${t.verdicts[suggestion.verdict]} — ${suggestion.reason}` : t.noReview}</p>
    </div>
    <h2>{t.evidenceAndUse}</h2>
    <div className="research-note-grid">
      <article><small>{t.supportingEvidence}</small>
        {draft.evidence.length ? draft.evidence.map((item, index) => <div key={index} className="note-evidence">
          <textarea className="note-edit" value={item.point} rows={3}
            onChange={(e) => set({ evidence: draft.evidence.map((ev, i) => i === index ? { ...ev, point: e.target.value } : ev) })} />
          <span className="ref-chips">{item.sources.map((s) => <button key={s.ref_id} className="ref-chip wide"
            onClick={() => onSource({ ...s, label: t.noteEvidence })}>{t.pageText(s)}</button>)}</span>
        </div>) : <p className="muted-text">{t.noEvidence}</p>}
      </article>
      <article><small>{t.possibleUse}</small>
        <textarea className="note-edit" value={draft.research_use} rows={6} onChange={(e) => set({ research_use: e.target.value })} /></article>
      <article><small>{t.adaptations}</small>
        <textarea className="note-edit" value={draft.adaptations_and_uncertainties} rows={6}
          onChange={(e) => set({ adaptations_and_uncertainties: e.target.value })} /></article>
      <article><small>{t.nextActions}</small>
        <textarea className="note-edit" value={draft.next_actions.join('\n')} rows={4}
          onChange={(e) => set({ next_actions: e.target.value.split('\n') })} /></article>
    </div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="form-actions note-actions">
      <span className="muted-text">{unsaved ? t.unsaved : draft.edited_by_learner ? t.editedSaved : t.draftedBy}</span>
      <button className="text-button" onClick={onGenerate} disabled={busy}>{t.redraft}</button>
      <button className="secondary-button" disabled={busy} onClick={() => void download()}>
        <Download aria-hidden="true" /> {unsaved ? t.saveAndDownload : t.downloadMd}</button>
      <button className="primary-button" disabled={busy || !unsaved} onClick={() => void onSave(fields())}>{t.saveNote}</button>
    </div>
  </div>;
}
