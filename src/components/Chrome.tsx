// Layout pieces carried over from the A1 prototype (header, composer, pickers, drawers), now wired to real data.
import { type FormEvent, type MouseEvent as ReactMouseEvent, type ReactNode, useEffect, useState } from 'react';
import { ChevronLeft, Download, Globe2, MessageSquarePlus, NotebookPen, Search, Send } from 'lucide-react';
import { api, type SessionSummary } from '../api';

export const RESEARCH_USE_GOAL = 'Explore potential use in my research';
export const OTHER_GOAL = 'Other — type a goal in the chat';
export const READING_GOALS = ['Get a general overview of this paper', 'Reproduce the study or method', RESEARCH_USE_GOAL, OTHER_GOAL];

const STARTER_QUESTIONS: Record<string, string[]> = {
  'Get a general overview of this paper': ["Summarise the paper's main argument.", 'What problem does this paper address?', 'What key concepts do I need to understand first?'],
  'Reproduce the study or method': ['What method or procedure does the paper use?', 'What data, participants or materials did the authors use?', 'What details would I need to reproduce this study?'],
  [RESEARCH_USE_GOAL]: ["Summarise the paper's main argument.", 'Which ideas in this paper could be relevant to my research?', "What are the limitations of the paper's approach?"],
};

export function IconButton({ label, onClick, children, disabled }: {
  label: string; onClick: (event: ReactMouseEvent<HTMLButtonElement>) => void; children: ReactNode; disabled?: boolean;
}) {
  return <button className="icon-button" onClick={onClick} aria-label={label} data-tooltip={label} disabled={disabled}>{children}</button>;
}

export function Header({ paperTitle, canExport, onHistory, onNew, onLanguage, onNotes, onExport }: {
  paperTitle: string | null; canExport: boolean; onHistory: () => void; onNew: () => void;
  onLanguage: (event: ReactMouseEvent<HTMLButtonElement>) => void; onNotes: () => void; onExport: () => void;
}) {
  return <header className="workspace-header">
    <div className="title-line">
      <button className="brand-title" onClick={onHistory} title="Open chat history">PaperLens</button>
      <span className="title-slash">/</span><span className="paper-title" title={paperTitle || undefined}>{paperTitle || 'Paper title'}</span>
    </div>
    <div className="header-actions">
      <IconButton label="Start a new conversation" onClick={onNew}><MessageSquarePlus /></IconButton>
      <IconButton label="Language settings" onClick={onLanguage}><Globe2 /></IconButton>
      <IconButton label="Research-use note" onClick={onNotes}><NotebookPen /></IconButton>
      <IconButton label="Export session log (JSON)" onClick={onExport} disabled={!canExport}><Download /></IconButton>
    </div>
  </header>;
}

export function Welcome() { return <div className="welcome"><p>Hello, Hongshan!</p><p>Let’s start reading a paper :)</p></div>; }

export function GoalPicker({ onChoose }: { onChoose: (goal: string) => void }) {
  return <div className="choice-screen"><h1>What would you like to learn?</h1><div className="choice-card">
    {READING_GOALS.map((item) => <button key={item} onClick={() => onChoose(item)}>{item}</button>)}
  </div></div>;
}

export function ResearchContextForm({ initial, onSubmit, onSkip, busy, compact }: {
  initial: string; onSubmit: (context: string) => void; onSkip?: () => void; busy?: boolean; compact?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return <form className={compact ? 'research-step context-form' : 'choice-screen context-form'}
    onSubmit={(event) => { event.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}>
    {compact ? <><small>YOUR RESEARCH</small><h2>Tell PaperLens about your research first</h2></>
      : <h1>What is your research about?</h1>}
    <p>Describe your research question, project or context in a few sentences. PaperLens uses it to judge relevance for <em>your</em> study.</p>
    <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={4}
      placeholder="e.g. I am studying how difficulty curves in mobile puzzle games affect whether casual players keep playing…" />
    <div className="form-actions">
      {onSkip && <button type="button" className="text-button" onClick={onSkip}>Skip for now</button>}
      <button type="submit" className="primary-button" disabled={!value.trim() || busy}>Save research context</button>
    </div>
  </form>;
}

export function PromptPicker({ goal, researchContext, onEditContext, onChoose }: {
  goal: string; researchContext: string; onEditContext: () => void; onChoose: (question: string) => void;
}) {
  const questions = STARTER_QUESTIONS[goal];
  return <div className="prompt-screen">
    {goal === RESEARCH_USE_GOAL && <article className="goal-overview">
      <small>YOUR RESEARCH CONTEXT</small>
      <p>{researchContext || 'Not provided yet. PaperLens will ask for it before judging relevance to your research.'}</p>
      <button className="text-button" onClick={onEditContext}>{researchContext ? 'Edit' : 'Add research context'}</button>
    </article>}
    {questions ? <>
      <h1>Choose a question to begin</h1>
      <div className="prompt-grid">{questions.map((item) => <button key={item} onClick={() => onChoose(item)}>{item}</button>)}</div>
      <p className="prompt-hint">…or type your own question below.</p>
    </> : <h1>Type your reading goal or first question below</h1>}
  </div>;
}

export function Composer({ draft, setDraft, onSubmit, disabled, placeholder }: {
  draft: string; setDraft: (value: string) => void; onSubmit: (event: FormEvent) => void; disabled: boolean; placeholder: string;
}) {
  return <form className="composer" onSubmit={onSubmit}>
    <textarea value={draft} onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}
      placeholder={placeholder} rows={1} disabled={disabled} aria-label="Message" />
    <button type="submit" className="send-button" aria-label="Send message" disabled={disabled || !draft.trim()}><Send /></button>
  </form>;
}

export function QuestionNavigator({ count, onSelect }: { count: number; onSelect: (index: number) => void }) {
  return <nav className="question-nav" aria-label="Jump to a question">
    {Array.from({ length: count }, (_, index) => <button key={index} onClick={() => onSelect(index)} aria-label={`Go to question ${index + 1}`} />)}
  </nav>;
}

export function HistoryDrawer({ currentId, onClose, onSelect }: {
  currentId: string | null; onClose: () => void; onSelect: (sessionId: string) => void;
}) {
  const [items, setItems] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.sessions().then(setItems).catch((e: Error) => setError(e.message)); }, []);
  return <aside className="history-drawer" aria-label="Chat history">
    <div className="drawer-heading"><h2>Chat history</h2><button onClick={onClose} aria-label="Close history"><ChevronLeft /></button></div>
    <small>THIS DEVICE</small>
    <div className="history-list">
      {error && <p className="inline-error">{error}</p>}
      {items && !items.length && <p className="muted-text">No saved sessions yet.</p>}
      {items?.map((item) => <button key={item.session_id} onClick={() => onSelect(item.session_id)}
        className={item.session_id === currentId ? 'active' : ''}>
        <small>{item.session_id === currentId ? 'CURRENT SESSION' : new Date(item.updated_at).toLocaleString()}</small>
        <span>{item.paper_title || 'Untitled paper'}</span>
        <small>{item.first_question || item.reading_goal}</small>
      </button>)}
    </div>
  </aside>;
}

export function LanguagePanel({ selected, position, onSelect, onClose }: {
  selected: string; position: { top: number; left: number }; onSelect: (value: string) => void; onClose: () => void;
}) {
  const languages = ['English', '中文（简体）', '中文（繁體）', '日本語'];
  return <div className="modal-scrim" onMouseDown={onClose}><section className="language-panel" aria-label="Language settings"
    style={{ top: position.top, left: position.left }} onMouseDown={(event) => event.stopPropagation()}>
    <div className="language-search"><Search /><span>Choose your preferred response language</span></div>
    {languages.map((item) => <button key={item} className={selected === item ? 'active' : ''} onClick={() => onSelect(item)}><span>{item}</span>{item === 'English' && <small>default</small>}</button>)}
    <p>Responses only · paper text stays unchanged</p>
  </section></div>;
}
