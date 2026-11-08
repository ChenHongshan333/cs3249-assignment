// Top-level state for the PaperLens workspace. All learning content comes from the backend (see src/api.ts).
import {
  type CSSProperties, type FormEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent,
  useEffect, useRef, useState,
} from 'react';
import { Search } from 'lucide-react';
import { api, type Paper, type Session, type TurnResult, type Verdict } from '../api';
import {
  Composer, GoalPicker, Header, HistoryDrawer, LanguagePanel, OTHER_GOAL, PromptPicker, QuestionNavigator,
  RESEARCH_USE_GOAL, ResearchContextForm, Welcome,
} from './Chrome';
import { Conversation, JudgmentStep, type PendingTurn } from './Conversation';
import { IndexingStatus, LandingUpload, PaperViewer, type SourceFocus } from './PaperPane';
import { SessionNotes } from './SessionNotes';

type Screen = 'landing' | 'indexing' | 'goals' | 'context' | 'prompts' | 'conversation' | 'notes';
const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

export function PaperLensWorkspace() {
  const [screen, setScreen] = useState<Screen>('landing');
  const [paper, setPaper] = useState<Paper | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [session, setSession] = useState<Session | null>(null);
  const [pendingGoal, setPendingGoal] = useState('');
  const [contextReturn, setContextReturn] = useState<Screen>('prompts');
  const [reviewNeedsContext, setReviewNeedsContext] = useState(false);
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [notesBusy, setNotesBusy] = useState(false);
  const [notesError, setNotesError] = useState('');
  const [focus, setFocus] = useState<SourceFocus | null>(null);
  const [draft, setDraft] = useState('');
  const [language, setLanguage] = useState('English');
  const [viewerWidth, setViewerWidth] = useState(460);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [languagePanelPosition, setLanguagePanelPosition] = useState<{ top: number; left: number } | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Array<HTMLDivElement | null>>([]);

  // ---------------------------------------------------------------- paper upload + indexing status
  const acceptUpload = async (upload: () => Promise<Paper>) => {
    setUploadBusy(true); setUploadError('');
    try {
      const meta = await upload();
      setPaper(meta);
      setScreen(meta.status === 'ready' ? 'goals' : 'indexing');
    } catch (error) {
      setUploadError(errorText(error));
    } finally {
      setUploadBusy(false);
    }
  };
  useEffect(() => {
    if (!paper || paper.status === 'ready' || paper.status === 'failed') return undefined;
    const timer = window.setInterval(() => {
      api.paper(paper.paper_id).then((next) => {
        setPaper(next);
        if (next.status === 'ready') setScreen((current) => (current === 'indexing' ? 'goals' : current));
      }).catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [paper]);
  const retryIndexing = async () => {
    if (!paper) return;
    try { setPaper(await api.retryPaper(paper.paper_id)); } catch (error) { setUploadError(errorText(error)); }
  };

  // ---------------------------------------------------------------- session setup
  const startSession = async (goal: string, researchContext = '') => {
    if (!paper) return;
    setActionError('');
    try {
      const created = await api.createSession({ paper_id: paper.paper_id, reading_goal: goal, research_context: researchContext, language });
      setSession(created);
      setScreen('prompts');
    } catch (error) { setActionError(errorText(error)); }
  };
  const chooseGoal = (goal: string) => {
    if (goal === RESEARCH_USE_GOAL) { setPendingGoal(goal); setContextReturn('prompts'); setScreen('context'); return; }
    void startSession(goal === OTHER_GOAL ? 'Other (described by the learner in chat)' : goal);
  };
  const saveContext = async (context: string) => {
    if (!session) { await startSession(pendingGoal, context); return; }
    try {
      setSession(await api.updateSession(session.session_id, { research_context: context }));
      setScreen(contextReturn);
    } catch (error) { setActionError(errorText(error)); }
  };

  // ---------------------------------------------------------------- turns (chat, critical review, judgment)
  const runTurn = async (text: string, mode: PendingTurn['mode'], call: () => Promise<TurnResult>) => {
    if (!session) return;
    const retry = () => { void runTurn(text, mode, call); };
    setPending({ text, mode, retry }); setBusy(true); setScreen('conversation'); setActionError('');
    try {
      const result = await call();
      setSession(await api.session(session.session_id));
      setPending(result.ok ? null : { text, mode, retry, error: result.error });
    } catch (error) {
      setPending({ text, mode, retry, error: errorText(error) });
      api.session(session.session_id).then(setSession).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };
  const ask = (question: string) => {
    if (!session || busy || !question.trim()) return;
    setDraft('');
    void runTurn(question.trim(), 'chat', () => api.sendMessage(session.session_id, question.trim()));
  };
  const submit = (event: FormEvent) => { event.preventDefault(); ask(draft); };
  const runCriticalReview = () => {
    if (!session || busy) return;
    if (!session.research_context) { setReviewNeedsContext(true); return; }
    void runTurn('Critically review whether the idea or method we have been discussing is applicable to my research.',
      'critical_review', () => api.criticalReview(session.session_id));
  };
  const saveContextThenReview = async (context: string) => {
    if (!session) return;
    try {
      const updated = await api.updateSession(session.session_id, { research_context: context });
      setSession(updated); setReviewNeedsContext(false);
      void runTurn('Critically review whether the idea or method we have been discussing is applicable to my research.',
        'critical_review', () => api.criticalReview(updated.session_id));
    } catch (error) { setActionError(errorText(error)); }
  };
  const submitJudgment = (verdict: Verdict, rationale: string) => {
    if (!session) return;
    void runTurn(`My verdict: ${verdict}\nMy rationale: ${rationale}`, 'judgment_feedback',
      () => api.submitJudgment(session.session_id, verdict, rationale));
  };

  // ---------------------------------------------------------------- notes
  const generateNote = async () => {
    if (!session) return;
    setNotesBusy(true); setNotesError('');
    try {
      const result = await api.generateNote(session.session_id);
      if (result.ok) setSession({ ...session, note: result.note }); else setNotesError(result.error);
    } catch (error) { setNotesError(errorText(error)); } finally { setNotesBusy(false); }
  };
  const saveNote = async (fields: Record<string, unknown>) => {
    if (!session) return;
    setNotesBusy(true); setNotesError('');
    try { setSession({ ...session, note: await api.saveNote(session.session_id, fields) }); }
    catch (error) { setNotesError(errorText(error)); } finally { setNotesBusy(false); }
  };

  // ---------------------------------------------------------------- header actions
  const newConversation = () => {
    setSession(null); setPaper(null); setPending(null); setBusy(false); setFocus(null); setDraft('');
    setReviewNeedsContext(false); setActionError(''); setUploadError(''); setNotesError(''); setPendingGoal('');
    setHistoryOpen(false); setLanguagePanelPosition(null); messageRefs.current = [];
    setScreen('landing');
  };
  const openSession = async (sessionId: string) => {
    setHistoryOpen(false);
    try {
      const loaded = await api.session(sessionId);
      setPaper(await api.paper(loaded.paper_id));
      setSession(loaded); setLanguage(loaded.language); setPending(null); setFocus(null); setReviewNeedsContext(false);
      setScreen(loaded.messages.length ? 'conversation' : 'prompts');
    } catch (error) { setActionError(errorText(error)); }
  };
  const openLanguage = (event: ReactMouseEvent<HTMLButtonElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const panelWidth = Math.min(375, window.innerWidth - 24);
    setLanguagePanelPosition({ top: rect.bottom + 10, left: Math.max(12, Math.min(rect.right - panelWidth, window.innerWidth - panelWidth - 12)) });
  };
  const chooseLanguage = (next: string) => {
    setLanguage(next); setLanguagePanelPosition(null);
    if (session) api.updateSession(session.session_id, { language: next }).then(setSession).catch((e) => setActionError(errorText(e)));
  };
  const exportLog = () => {
    if (!session) return;
    const link = document.createElement('a');
    link.href = api.exportUrl(session.session_id);
    link.download = `paperlens-${session.session_id}.json`;
    link.click();
  };
  const startResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startWidth = viewerWidth;
    const onMove = (moveEvent: PointerEvent) => setViewerWidth(Math.max(320, Math.min(760, startWidth + moveEvent.clientX - startX)));
    const onUp = () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const messages = session?.messages ?? [];
  useEffect(() => {
    if (screen === 'conversation') contentRef.current?.scrollTo({ top: contentRef.current.scrollHeight, behavior: 'smooth' });
    else contentRef.current?.scrollTo({ top: 0 });
  }, [messages.length, pending, screen]);

  const hasAnswer = messages.some((m) => m.role === 'assistant' && m.mode === 'chat');
  const reviewDone = messages.some((m) => m.role === 'assistant' && m.mode === 'critical_review');
  const questionCount = messages.filter((m) => m.role === 'user').length + (pending ? 1 : 0);
  const composerEnabled = !!session && !busy && (screen === 'prompts' || screen === 'conversation');
  const judgmentStep = reviewNeedsContext
    ? <ResearchContextForm compact initial={session?.research_context ?? ''} onSubmit={saveContextThenReview}
      onSkip={() => setReviewNeedsContext(false)} />
    : reviewDone && session
      ? <JudgmentStep key={session.judgment?.submitted_at ?? 'new'} suggestion={session.system_suggestion} judgment={session.judgment}
        busy={busy} onSubmit={submitJudgment} onCreateNote={() => setScreen('notes')} />
      : null;

  return (
    <main className="paperlens-workspace" style={{ '--viewer-width': `${viewerWidth}px` } as CSSProperties}>
      <section className="paper-pane" aria-label="Paper viewer">
        {paper
          ? <PaperViewer pdfUrl={api.pdfUrl(paper.paper_id)} focus={focus} onCloseFocus={() => setFocus(null)} />
          : <LandingUpload busy={uploadBusy} error={uploadError}
            onFile={(file) => void acceptUpload(() => api.uploadPaper(file))}
            onUrl={(url) => void acceptUpload(() => api.uploadPaperUrl(url))} />}
      </section>
      <button className="splitter" onPointerDown={startResize} aria-label="Resize paper and conversation panels">
        <span aria-hidden="true">›</span>
      </button>
      <section className="reading-pane">
        <Header paperTitle={paper?.title ?? null} canExport={!!session}
          onHistory={() => setHistoryOpen(true)} onNew={newConversation}
          onLanguage={openLanguage} onNotes={() => session && setScreen('notes')} onExport={exportLog} />
        <div className="reading-body" ref={contentRef}>
          {session?.reading_goal && screen !== 'notes' && <div className="goal-chip">Goal: {session.reading_goal}</div>}
          {actionError && <p className="inline-error banner" role="alert">{actionError}</p>}
          {screen === 'landing' && <Welcome />}
          {screen === 'indexing' && paper && <IndexingStatus paper={paper} onRetry={retryIndexing} onUploadAnother={newConversation} />}
          {screen === 'goals' && <GoalPicker onChoose={chooseGoal} />}
          {screen === 'context' && <ResearchContextForm initial={session?.research_context ?? ''} onSubmit={saveContext}
            onSkip={() => (session ? setScreen(contextReturn) : void startSession(pendingGoal))} />}
          {screen === 'prompts' && session && <PromptPicker goal={session.reading_goal} researchContext={session.research_context}
            onEditContext={() => { setContextReturn('prompts'); setScreen('context'); }} onChoose={ask} />}
          {screen === 'conversation' && <Conversation messages={messages} pending={pending} refs={messageRefs} busy={busy}
            onSource={setFocus} onFollowUp={ask} judgmentStep={judgmentStep} />}
          {screen === 'notes' && <SessionNotes session={session} busy={notesBusy} error={notesError}
            onGenerate={generateNote} onSave={saveNote} onSource={setFocus}
            onBack={() => setScreen(messages.length ? 'conversation' : session ? 'prompts' : 'landing')} />}
        </div>
        {screen !== 'notes' && <Composer draft={draft} setDraft={setDraft} onSubmit={submit} disabled={!composerEnabled}
          placeholder={!paper ? 'Load a paper to start a conversation…' : !session ? 'Choose a reading goal first…' : busy ? 'PaperLens is answering…' : 'Ask about the paper…'} />}
        {screen === 'conversation' && hasAnswer && !reviewDone && !reviewNeedsContext && !busy && (
          <button className="critical-review-launcher" onClick={runCriticalReview}>
            <Search aria-hidden="true" />
            <span><strong>Critical review</strong><small>Evaluate applicability to my research</small></span>
          </button>
        )}
        {screen === 'conversation' && questionCount > 0 && (
          <QuestionNavigator count={questionCount} onSelect={(index) => messageRefs.current[index]?.scrollIntoView({ behavior: 'smooth', block: 'start' })} />
        )}
      </section>
      {historyOpen && <HistoryDrawer currentId={session?.session_id ?? null} onClose={() => setHistoryOpen(false)} onSelect={openSession} />}
      {languagePanelPosition && <LanguagePanel selected={language} position={languagePanelPosition}
        onSelect={chooseLanguage} onClose={() => setLanguagePanelPosition(null)} />}
    </main>
  );
}
