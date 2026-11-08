// Conversation thread: layered answers with verifiable sources, plus the research-use judgment step.
import { type ReactNode, type RefObject, useState } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { pageText, VERDICTS, type AssistantMessage, type Judgment, type Message, type SectionKind, type Source, type SystemSuggestion, type Verdict } from '../api';
import type { SourceFocus } from './PaperPane';

export type PendingTurn = { text: string; mode: Message['mode']; error?: string; retry: () => void };

const KIND_LABEL: Record<SectionKind, string> = {
  paper: 'From the paper',
  explanation: 'Explanation',
  example: 'Illustrative example · not from the paper',
  inference: 'PaperLens inference',
  research_use: 'For your research',
  limitation: 'Limitation / uncertainty',
};

const MODE_LABEL: Record<Message['mode'], string> = {
  chat: '', critical_review: 'Critical review request', judgment_feedback: 'My research-use decision',
};

function RefChips({ refs, sources, onSource }: { refs: string[]; sources: Source[]; onSource: (s: SourceFocus) => void }) {
  if (!refs.length) return null;
  return <span className="ref-chips">{refs.map((ref) => {
    const index = sources.findIndex((s) => s.ref_id === ref);
    const source = sources[index];
    if (!source) return null;
    return <button key={ref} className={`ref-chip ${source.verified ? '' : 'unverified'}`} title={pageText(source)}
      disabled={!source.verified} onClick={() => onSource({ ...source, label: `Source ${index + 1}` })}>{index + 1}</button>;
  })}</span>;
}

function EvidenceNotice({ message }: { message: AssistantMessage }) {
  if (message.evidence_status === 'insufficient') {
    return <p className="evidence-notice"><AlertTriangle aria-hidden="true" />The passages PaperLens found are not enough to confirm this. This does not mean the paper never discusses it — try a more specific question.</p>;
  }
  if (message.evidence_status === 'partial') {
    return <p className="evidence-notice subtle"><AlertTriangle aria-hidden="true" />Only partly supported by the passages found. Check the sources before relying on it.</p>;
  }
  if (!message.has_verified_paper_source) {
    return <p className="evidence-notice subtle"><AlertTriangle aria-hidden="true" />No original paper passage is cited for this answer.</p>;
  }
  return null;
}

function SuggestionBox({ suggestion }: { suggestion: SystemSuggestion }) {
  return <div className="system-suggestion">
    <small>PAPERLENS SUGGESTION · NOT YOUR DECISION</small>
    <p><strong>{suggestion.verdict}</strong> — {suggestion.reason}</p>
  </div>;
}

function AssistantBubble({ message, latest, busy, onSource, onFollowUp }: {
  message: AssistantMessage; latest: boolean; busy: boolean; onSource: (s: SourceFocus) => void; onFollowUp: (q: string) => void;
}) {
  return <>
    <div className="message-copy">{message.short_answer}<RefChips refs={message.short_answer_refs} sources={message.sources} onSource={onSource} /></div>
    <EvidenceNotice message={message} />
    {message.clarifying_question && <p className="clarifying-question"><small>PAPERLENS ASKS</small>{message.clarifying_question}</p>}
    {message.system_suggestion && <SuggestionBox suggestion={message.system_suggestion} />}
    {message.sections.length > 0 && <div className="answer-layers" aria-label="Expandable answer layers">
      {message.sections.map((section, index) => <details key={`${section.title}-${index}`}>
        <summary><span className="layer-title">{section.title}<em className={`kind-tag ${section.kind}`}>{KIND_LABEL[section.kind]}</em></span><span aria-hidden="true">+</span></summary>
        <p>{section.text}<RefChips refs={section.refs} sources={message.sources} onSource={onSource} /></p>
      </details>)}
    </div>}
    {message.sources.length > 0 && <div className="source-list">
      <small>SOURCES</small>
      {message.sources.map((source, index) => <button key={source.ref_id} className={`source-link ${source.verified ? '' : 'unverified'}`}
        disabled={!source.verified} onClick={() => onSource({ ...source, label: `Source ${index + 1}` })}>
        <span>[{index + 1}] {source.kind === 'overview' ? 'GENERATED OVERVIEW · ' : ''}{source.verified ? pageText(source).toUpperCase() : 'UNVERIFIED ID'}</span>
        <strong>{source.verified ? (source.text ?? '').slice(0, 90) + '…' : source.ref_id}</strong>
        <span aria-hidden="true">→</span>
      </button>)}
    </div>}
    {latest && !busy && message.follow_up_suggestions.length > 0 && <div className="follow-up-suggestions">
      <small>FOLLOW UP</small>
      <div>{message.follow_up_suggestions.map((q) => <button key={q} onClick={() => onFollowUp(q)}>{q}</button>)}</div>
    </div>}
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
  let questionIndex = -1;
  const latestAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id;
  const userRef = (index: number) => (node: HTMLDivElement | null) => { refs.current[index] = node; };
  return <div className="conversation">
    {messages.map((message) => {
      if (message.role === 'user') {
        questionIndex += 1;
        return <div key={message.id} ref={userRef(questionIndex)} className={`message user ${message.mode}`}>
          {MODE_LABEL[message.mode] && <small className="message-mode">{MODE_LABEL[message.mode]}</small>}
          <div className="message-copy">{message.text}</div>
        </div>;
      }
      return <div key={message.id} className={`message assistant ${message.mode}`}>
        <AssistantBubble message={message} latest={message.id === latestAssistantId} busy={busy} onSource={onSource} onFollowUp={onFollowUp} />
      </div>;
    })}
    {pending && <>
      <div ref={userRef(questionIndex + 1)} className={`message user ${pending.mode} ${pending.error ? 'failed' : ''}`}>
        {MODE_LABEL[pending.mode] && <small className="message-mode">{MODE_LABEL[pending.mode]}</small>}
        <div className="message-copy">{pending.text}</div>
      </div>
      {pending.error
        ? <div className="message assistant turn-error" role="alert">
          <p><AlertTriangle aria-hidden="true" />PaperLens could not answer: {pending.error}</p>
          <button className="primary-button" onClick={pending.retry}><RotateCcw aria-hidden="true" /> Retry</button>
        </div>
        : <div className="message assistant thinking"><span /><span /><span /></div>}
    </>}
    {!busy && judgmentStep}
  </div>;
}

export function JudgmentStep({ suggestion, judgment, busy, onSubmit, onCreateNote }: {
  suggestion: SystemSuggestion | null; judgment: Judgment | null; busy: boolean;
  onSubmit: (verdict: Verdict, rationale: string) => void; onCreateNote: () => void;
}) {
  const [editing, setEditing] = useState(!judgment);
  const [verdict, setVerdict] = useState<Verdict | null>(judgment?.verdict ?? null);
  const [rationale, setRationale] = useState(judgment?.rationale ?? '');
  if (judgment && !editing) {
    return <section className="research-step judgment-step">
      <small>LEARNER JUDGMENT</small>
      <div className="judgment-confirmation">
        <span>Your decision: <strong>{judgment.verdict}</strong><br /><em>“{judgment.rationale}”</em></span>
        <button onClick={onCreateNote}>Create research-use note <span aria-hidden="true">→</span></button>
      </div>
      <button className="text-button" onClick={() => setEditing(true)}>Revise my decision</button>
    </section>;
  }
  return <form className="research-step judgment-step" onSubmit={(event) => {
    event.preventDefault();
    if (verdict && rationale.trim().length >= 10) { onSubmit(verdict, rationale.trim()); setEditing(false); }
  }}>
    <small>LEARNER JUDGMENT</small>
    <h2>How will you use this idea?</h2>
    <p>PaperLens has organised the evidence{suggestion ? ' and made a suggestion above' : ''}. The final research-use decision and the reasons are yours.</p>
    <div className="judgment-options">
      {VERDICTS.map((option) => <button type="button" key={option} className={verdict === option ? 'selected' : ''}
        aria-pressed={verdict === option} onClick={() => setVerdict(option)}>{option}</button>)}
    </div>
    <label className="rationale-field">
      <span>Your reason, in your own words</span>
      <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} rows={3}
        placeholder="Why did you choose this? Which evidence or limitation matters most for your study?" />
    </label>
    <div className="form-actions">
      <button type="submit" className="primary-button" disabled={busy || !verdict || rationale.trim().length < 10}>Record my decision</button>
    </div>
  </form>;
}
