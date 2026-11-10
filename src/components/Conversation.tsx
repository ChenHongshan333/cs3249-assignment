// Conversation thread: layered answers with verifiable sources, plus the research-use judgment step.
import { type ReactNode, type RefObject, useState } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { VERDICTS, type AssistantMessage, type Judgment, type Message, type Source, type SystemSuggestion, type Verdict } from '../api';
import { displayUserMessage, figureParts, sourceText, useT } from '../i18n';
import type { SourceFocus } from './PaperPane';

export type PendingTurn = { text: string; mode: Message['mode']; error?: string; retry: () => void };

function RefChips({ refs, sources, onSource }: { refs: string[]; sources: Source[]; onSource: (s: SourceFocus) => void }) {
  const t = useT();
  if (!refs.length) return null;
  return <span className="ref-chips">{refs.map((ref) => {
    const index = sources.findIndex((s) => s.ref_id === ref);
    const source = sources[index];
    if (!source) return null;
    return <button key={ref} className={`ref-chip ${source.verified ? '' : 'unverified'}`} title={sourceText(t, source)}
      disabled={!source.verified} onClick={() => onSource({ ...source, focusLabel: t.sourceN(index + 1) })}>{index + 1}</button>;
  })}</span>;
}

function EvidenceNotice({ message }: { message: AssistantMessage }) {
  const t = useT();
  if (message.evidence_status === 'insufficient') {
    return <p className="evidence-notice"><AlertTriangle aria-hidden="true" />{t.evidenceInsufficient}</p>;
  }
  if (message.evidence_status === 'partial') {
    return <p className="evidence-notice subtle"><AlertTriangle aria-hidden="true" />{t.evidencePartial}</p>;
  }
  if (!message.has_verified_paper_source) {
    return <p className="evidence-notice subtle"><AlertTriangle aria-hidden="true" />{t.evidenceNoPaper}</p>;
  }
  return null;
}

function SuggestionBox({ suggestion }: { suggestion: SystemSuggestion }) {
  const t = useT();
  return <div className="system-suggestion">
    <small>{t.suggestionTitle}</small>
    <p><strong>{t.verdicts[suggestion.verdict] ?? suggestion.verdict}</strong> — {suggestion.reason}</p>
  </div>;
}

/** Original passages and PaperLens summaries are listed separately; numbers match the chips in the answer. */
function SourceList({ sources, onSource }: { sources: Source[]; onSource: (s: SourceFocus) => void }) {
  const t = useT();
  if (!sources.length) return null;
  const numbered = sources.map((source, index) => ({ source, number: index + 1 }));
  const groups = [
    { key: 'paper', title: t.fromThePaper, items: numbered.filter((s) => s.source.kind === 'paper' || s.source.kind === 'unknown') },
    { key: 'figure', title: t.figuresTitle, items: numbered.filter((s) => s.source.kind === 'figure') },
    { key: 'overview', title: t.summariesTitle, items: numbered.filter((s) => s.source.kind === 'overview') },
  ].filter((group) => group.items.length);
  const previewOf = (source: Source) => {
    if (source.quotes?.[0]) return `“${source.quotes[0]}”`;
    if (source.kind === 'figure') return source.caption ? `“${source.caption}”` : `${figureParts(source).description.slice(0, 110)}…`;
    return `${(source.text ?? '').slice(0, 110)}…`;
  };
  return <div className="source-list">
    {groups.map((group) => <div key={group.key} className="source-group">
      <small>{group.title}</small>
      {group.items.map(({ source, number }) => {
        const preview = previewOf(source);
        return <button key={source.ref_id} className={`source-link ${source.verified ? '' : 'unverified'}`}
          disabled={!source.verified} onClick={() => onSource({ ...source, focusLabel: t.sourceN(number) })}>
          <span>[{number}] {source.verified ? sourceText(t, source).toUpperCase() : t.unverifiedId}</span>
          <strong>{source.verified ? preview : source.ref_id}</strong>
          <span aria-hidden="true">→</span>
        </button>;
      })}
    </div>)}
  </div>;
}

function AssistantBubble({ message, latest, busy, onSource, onFollowUp }: {
  message: AssistantMessage; latest: boolean; busy: boolean; onSource: (s: SourceFocus) => void; onFollowUp: (q: string) => void;
}) {
  const t = useT();
  return <>
    <div className="message-copy">{message.short_answer}<RefChips refs={message.short_answer_refs} sources={message.sources} onSource={onSource} /></div>
    <EvidenceNotice message={message} />
    {message.clarifying_question && <p className="clarifying-question"><small>{t.paperlensAsks}</small>{message.clarifying_question}</p>}
    {message.system_suggestion && <SuggestionBox suggestion={message.system_suggestion} />}
    {message.sections.length > 0 && <div className="answer-layers" aria-label={t.answerLayers}>
      {message.sections.map((section, index) => <details key={`${section.title}-${index}`}>
        <summary><span className="layer-title">{section.title}<em className={`kind-tag ${section.kind}`}>{t.kinds[section.kind]}</em></span><span className="layer-toggle" aria-hidden="true">+</span></summary>
        <p>{section.text}<RefChips refs={section.refs} sources={message.sources} onSource={onSource} /></p>
      </details>)}
    </div>}
    <SourceList sources={message.sources} onSource={onSource} />
    {latest && !busy && message.follow_up_suggestions.length > 0 && <div className="follow-up-suggestions">
      <small>{t.followUp}</small>
      <div>{message.follow_up_suggestions.map((q) => <button key={q} onClick={() => onFollowUp(q)}>{q}</button>)}</div>
    </div>}
  </>;
}

function UserBubble({ mode, text }: { mode: Message['mode']; text: string }) {
  const t = useT();
  const label = mode === 'critical_review' ? t.criticalReviewRequestLabel : mode === 'judgment_feedback' ? t.judgmentLabel : '';
  return <>
    {label && <small className="message-mode">{label}</small>}
    <div className="message-copy">{displayUserMessage(t, mode, text)}</div>
  </>;
}

export function Conversation({ messages, pending, refs, busy, onSource, onFollowUp, judgmentStep }: {
  messages: Message[];
  pending: PendingTurn | null;
  refs: RefObject<Array<HTMLDivElement | null>>;
  busy: boolean;
  onSource: (source: SourceFocus) => void;
  onFollowUp: (question: string) => void;
  judgmentStep: ReactNode;
}) {
  const t = useT();
  let questionIndex = -1;
  const latestAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id;
  const userRef = (index: number) => (node: HTMLDivElement | null) => { refs.current[index] = node; };
  return <div className="conversation">
    {messages.map((message) => {
      if (message.role === 'user') {
        questionIndex += 1;
        return <div key={message.id} ref={userRef(questionIndex)} className={`message user ${message.mode}`}>
          <UserBubble mode={message.mode} text={message.text} />
        </div>;
      }
      return <div key={message.id} className={`message assistant ${message.mode}`}>
        <AssistantBubble message={message} latest={message.id === latestAssistantId} busy={busy} onSource={onSource} onFollowUp={onFollowUp} />
      </div>;
    })}
    {pending && <>
      <div ref={userRef(questionIndex + 1)} className={`message user ${pending.mode} ${pending.error ? 'failed' : ''}`}>
        <UserBubble mode={pending.mode} text={pending.text} />
      </div>
      {pending.error
        ? <div className="message assistant turn-error" role="alert">
          <p><AlertTriangle aria-hidden="true" />{t.couldNotAnswer(pending.error)}</p>
          <button className="primary-button" onClick={pending.retry}><RotateCcw aria-hidden="true" /> {t.retry}</button>
        </div>
        : <div className="message assistant thinking" role="status">
          <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
          <span className="thinking-label">{t.thinking}</span>
        </div>}
    </>}
    {!busy && judgmentStep}
  </div>;
}

export function JudgmentStep({ suggestion, judgment, busy, onSubmit, onCreateNote }: {
  suggestion: SystemSuggestion | null; judgment: Judgment | null; busy: boolean;
  onSubmit: (verdict: Verdict, rationale: string) => void; onCreateNote: () => void;
}) {
  const t = useT();
  const [editing, setEditing] = useState(!judgment);
  const [verdict, setVerdict] = useState<Verdict | null>(judgment?.verdict ?? null);
  const [rationale, setRationale] = useState(judgment?.rationale ?? '');
  if (judgment && !editing) {
    return <section className="research-step judgment-step">
      <small>{t.learnerJudgment}</small>
      <div className="judgment-confirmation">
        <span>{t.yourDecision} <strong>{t.verdicts[judgment.verdict]}</strong><br /><em>“{judgment.rationale}”</em></span>
        <button onClick={onCreateNote}>{t.createNote} <span aria-hidden="true">→</span></button>
      </div>
      <button className="text-button" onClick={() => setEditing(true)}>{t.revise}</button>
    </section>;
  }
  return <form className="research-step judgment-step" onSubmit={(event) => {
    event.preventDefault();
    if (verdict && rationale.trim().length >= 10) { onSubmit(verdict, rationale.trim()); setEditing(false); }
  }}>
    <small>{t.learnerJudgment}</small>
    <h2>{t.howUse}</h2>
    <p>{t.judgmentIntro(!!suggestion)}</p>
    <div className="judgment-options">
      {VERDICTS.map((option) => <button type="button" key={option} className={verdict === option ? 'selected' : ''}
        aria-pressed={verdict === option} onClick={() => setVerdict(option)}>{t.verdicts[option]}</button>)}
    </div>
    <label className="rationale-field">
      <span>{t.yourReason}</span>
      <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} rows={3} placeholder={t.rationalePlaceholder} />
    </label>
    <div className="form-actions">
      <button type="submit" className="primary-button" disabled={busy || !verdict || rationale.trim().length < 10}>{t.recordDecision}</button>
    </div>
  </form>;
}
