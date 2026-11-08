// Layout pieces carried over from the A1 prototype (header, composer, pickers, drawers), now wired to real data.
// All functional text comes from src/i18n.ts; "PaperLens" and paper titles are never translated.
import { type FormEvent, type MouseEvent as ReactMouseEvent, type ReactNode, useEffect, useState } from 'react';
import { ALargeSmall, ChevronLeft, Download, Globe2, MessageSquarePlus, NotebookPen, Search, Send, Trash2 } from 'lucide-react';
import { api, type SessionSummary } from '../api';
import { GOAL_RESEARCH, GOALS, LANGUAGES, type Language, useT } from '../i18n';

export type MenuPosition = { top: number; left: number };
type HeaderMenuHandler = (event: ReactMouseEvent<HTMLButtonElement>) => void;

/** Place a popover under the clicked header button, kept inside the window. */
export function menuPositionFor(event: ReactMouseEvent<HTMLButtonElement>, width = 375): MenuPosition {
  const rect = event.currentTarget.getBoundingClientRect();
  const panelWidth = Math.min(width, window.innerWidth - 24);
  return { top: rect.bottom + 10, left: Math.max(12, Math.min(rect.right - panelWidth, window.innerWidth - panelWidth - 12)) };
}

export function IconButton({ label, onClick, children, disabled }: {
  label: string; onClick: (event: ReactMouseEvent<HTMLButtonElement>) => void; children: ReactNode; disabled?: boolean;
}) {
  return <button className="icon-button" onClick={onClick} aria-label={label} data-tooltip={label} disabled={disabled}>{children}</button>;
}

export function Header({ paperTitle, canExport, onHistory, onNew, onLanguage, onTextSize, onNotes, onExport }: {
  paperTitle: string | null; canExport: boolean; onHistory: () => void; onNew: () => void;
  onLanguage: HeaderMenuHandler; onTextSize: HeaderMenuHandler; onNotes: () => void; onExport: HeaderMenuHandler;
}) {
  const t = useT();
  return <header className="workspace-header">
    <div className="title-line">
      <button className="brand-title" onClick={onHistory} title={t.openHistory}>PaperLens</button>
      <span className="title-slash">/</span>
      <span className={`paper-title ${(paperTitle ?? '').length > 70 ? 'long' : ''}`} title={paperTitle || undefined}>
        {paperTitle || t.paperTitlePlaceholder}</span>
    </div>
    <div className="header-actions">
      <IconButton label={t.newConversation} onClick={onNew}><MessageSquarePlus /></IconButton>
      <IconButton label={t.languageSettings} onClick={onLanguage}><Globe2 /></IconButton>
      <IconButton label={t.textSize} onClick={onTextSize}><ALargeSmall /></IconButton>
      <IconButton label={t.researchNote} onClick={onNotes}><NotebookPen /></IconButton>
      <IconButton label={t.downloadMenu} onClick={onExport} disabled={!canExport}><Download /></IconButton>
    </div>
  </header>;
}

export function Welcome() {
  const t = useT();
  return <div className="welcome"><p>{t.welcome[0]}</p><p>{t.welcome[1]}</p></div>;
}

export function GoalPicker({ onChoose }: { onChoose: (goal: string) => void }) {
  const t = useT();
  return <div className="choice-screen"><h1>{t.goalQuestion}</h1><div className="choice-card">
    {GOALS.map((goal) => <button key={goal} onClick={() => onChoose(goal)}>{t.goals[goal]}</button>)}
  </div></div>;
}

export function ResearchContextForm({ initial, onSubmit, onSkip, busy, compact }: {
  initial: string; onSubmit: (context: string) => void; onSkip?: () => void; busy?: boolean; compact?: boolean;
}) {
  const t = useT();
  const [value, setValue] = useState(initial);
  return <form className={compact ? 'research-step context-form' : 'choice-screen context-form'}
    onSubmit={(event) => { event.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}>
    {compact ? <><small>{t.yourResearchSmall}</small><h2>{t.contextCompactTitle}</h2></> : <h1>{t.contextTitle}</h1>}
    <p>{t.contextHelp}</p>
    <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={4} placeholder={t.contextPlaceholder} />
    <div className="form-actions">
      {onSkip && <button type="button" className="text-button" onClick={onSkip}>{t.skipForNow}</button>}
      <button type="submit" className="primary-button" disabled={!value.trim() || busy}>{t.saveContext}</button>
    </div>
  </form>;
}

export function PromptPicker({ goal, researchContext, onEditContext, onChoose }: {
  goal: string; researchContext: string; onEditContext: () => void; onChoose: (question: string) => void;
}) {
  const t = useT();
  const questions = t.starterQuestions[goal];
  return <div className="prompt-screen">
    {goal === GOAL_RESEARCH && <article className="goal-overview">
      <small>{t.researchContextSmall}</small>
      <p>{researchContext || t.contextMissing}</p>
      <button className="text-button" onClick={onEditContext}>{researchContext ? t.edit : t.addContext}</button>
    </article>}
    {questions ? <>
      <h1>{t.chooseQuestion}</h1>
      <div className="prompt-grid">{questions.map((item) => <button key={item} onClick={() => onChoose(item)}>{item}</button>)}</div>
      <p className="prompt-hint">{t.orTypeOwn}</p>
    </> : <h1>{t.typeGoal}</h1>}
  </div>;
}

export function Composer({ draft, setDraft, onSubmit, disabled, placeholder }: {
  draft: string; setDraft: (value: string) => void; onSubmit: (event: FormEvent) => void; disabled: boolean; placeholder: string;
}) {
  const t = useT();
  return <form className="composer" onSubmit={onSubmit}>
    <textarea value={draft} onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => {
        // Enter sends, but not while an input method (e.g. Chinese/Japanese IME) is composing text.
        if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
          event.preventDefault(); event.currentTarget.form?.requestSubmit();
        }
      }}
      placeholder={placeholder} rows={1} disabled={disabled} aria-label={t.messageLabel} />
    <button type="submit" className="send-button" aria-label={t.send} disabled={disabled || !draft.trim()}><Send /></button>
  </form>;
}

export function QuestionNavigator({ count, onSelect }: { count: number; onSelect: (index: number) => void }) {
  const t = useT();
  return <nav className="question-nav" aria-label={t.jumpToQuestion}>
    {Array.from({ length: count }, (_, index) => <button key={index} onClick={() => onSelect(index)} aria-label={t.goToQuestion(index + 1)} />)}
  </nav>;
}

export function HistoryDrawer({ currentId, onClose, onSelect, onDeleted }: {
  currentId: string | null; onClose: () => void; onSelect: (sessionId: string) => void; onDeleted: (sessionId: string) => void;
}) {
  const t = useT();
  const [items, setItems] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  useEffect(() => { api.sessions().then(setItems).catch((e: Error) => setError(e.message)); }, []);
  const remove = async (sessionId: string) => {
    setDeleting(true); setError('');
    try {
      await api.deleteSession(sessionId);
      setItems((current) => current?.filter((item) => item.session_id !== sessionId) ?? null);
      setConfirming(null);
      onDeleted(sessionId);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setDeleting(false); }
  };
  return <aside className="history-drawer" aria-label={t.historyTitle}
    onKeyDown={(event) => { if (event.key === 'Escape') { if (confirming) setConfirming(null); else onClose(); } }}>
    <div className="drawer-heading"><h2>{t.historyTitle}</h2><button onClick={onClose} aria-label={t.closeHistory}><ChevronLeft /></button></div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="history-list">
      {items && !items.length && <p className="muted-text">{t.noSessions}</p>}
      {items?.map((item) => {
        const current = item.session_id === currentId;
        const title = item.paper_title || t.untitledPaper;
        if (confirming === item.session_id) {
          return <div key={item.session_id} className="history-item confirming" role="group" aria-label={t.deleteConfirm}>
            <p>{t.deleteConfirm}<small>{t.deleteHint}</small></p>
            <div className="form-actions">
              <button className="text-button" onClick={() => setConfirming(null)} autoFocus>{t.cancel}</button>
              <button className="primary-button danger" disabled={deleting} onClick={() => void remove(item.session_id)}>{t.delete}</button>
            </div>
          </div>;
        }
        return <div key={item.session_id} className={`history-item ${current ? 'active' : ''}`}
          onContextMenu={(event) => { event.preventDefault(); setConfirming(item.session_id); }}>
          <button className="history-entry" onClick={() => onSelect(item.session_id)}>
            <small>{current ? t.currentSession : new Date(item.updated_at).toLocaleString(t.locale)}</small>
            <span>{title}</span>
            <small>{item.first_question || t.goals[item.reading_goal] || item.reading_goal}</small>
          </button>
          <button className="history-delete" onClick={() => setConfirming(item.session_id)}
            aria-label={t.deleteSessionOf(title)} title={t.deleteSession}><Trash2 /></button>
        </div>;
      })}
    </div>
  </aside>;
}

export type MenuItem = { label: string; description?: string; active?: boolean; disabled?: boolean; onSelect: () => void };

/** Small popover menu used by the text-size and download header buttons. */
export function PopoverMenu({ label, position, items, onClose }: {
  label: string; position: MenuPosition; items: MenuItem[]; onClose: () => void;
}) {
  return <div className="modal-scrim" onMouseDown={onClose}>
    <section className="menu-panel" role="menu" aria-label={label} style={{ top: position.top, left: position.left }}
      onMouseDown={(event) => event.stopPropagation()}
      onKeyDown={(event) => { if (event.key === 'Escape') onClose(); }}>
      <small>{label}</small>
      {items.map((item) => <button key={item.label} role="menuitem" className={item.active ? 'active' : ''}
        disabled={item.disabled} onClick={() => { item.onSelect(); onClose(); }}>
        <span>{item.label}</span>{item.description && <small>{item.description}</small>}
      </button>)}
    </section>
  </div>;
}

export function LanguagePanel({ selected, position, onSelect, onClose }: {
  selected: Language; position: MenuPosition; onSelect: (value: Language) => void; onClose: () => void;
}) {
  const t = useT();
  return <div className="modal-scrim" onMouseDown={onClose}><section className="language-panel" aria-label={t.languageSettings}
    style={{ top: position.top, left: position.left }} onMouseDown={(event) => event.stopPropagation()}
    onKeyDown={(event) => { if (event.key === 'Escape') onClose(); }}>
    <div className="language-search"><Search /><span>{t.languageTitle}</span></div>
    {LANGUAGES.map((item) => <button key={item} className={selected === item ? 'active' : ''} onClick={() => onSelect(item)}>
      <span>{item}</span>{item === 'English' && <small>{t.languageDefault}</small>}</button>)}
    <p>{t.languageNote}</p>
  </section></div>;
}
