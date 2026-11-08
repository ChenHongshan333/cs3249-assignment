// Left pane (upload + PDF viewer) and the indexing status shown while a paper is processed.
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, FilePlus2, LoaderCircle, X } from 'lucide-react';
import { pageText, type Paper, type Source } from '../api';
import { type HighlightStatus, type PdfTarget, PdfViewer } from './PdfViewer';

export type SourceFocus = Source & { label: string };

export function LandingUpload({ onFile, onUrl, busy, error }: {
  onFile: (file: File) => void; onUrl: (url: string) => void; busy: boolean; error: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [paperUrl, setPaperUrl] = useState('');
  const [localError, setLocalError] = useState('');
  const acceptFile = (file?: File) => {
    if (!file || busy) return;
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setLocalError('Please choose a PDF file.');
      return;
    }
    setLocalError('');
    onFile(file);
  };
  const browse = () => inputRef.current?.click();
  const shownError = localError || error;
  return <div className="upload-page"><div className="upload-card" role="button" tabIndex={0} onClick={browse} aria-busy={busy}
    onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); browse(); } }}
    onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }}
    onDrop={(event) => { event.preventDefault(); acceptFile(event.dataTransfer.files[0]); }}>
    <input ref={inputRef} className="file-input" type="file" accept="application/pdf,.pdf" onClick={(event) => event.stopPropagation()}
      aria-label="Choose a PDF file" onChange={(event) => { acceptFile(event.target.files?.[0]); event.target.value = ''; }} />
    {busy ? <LoaderCircle className="spin" aria-hidden="true" /> : <FilePlus2 aria-hidden="true" />}
    <span>{busy ? 'Uploading…' : <>Drop a PDF here<br />or click to browse</>}</span>
    <span className="url-field" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
      <input value={paperUrl} onChange={(event) => setPaperUrl(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Enter' && paperUrl.trim()) onUrl(paperUrl.trim()); }}
        placeholder="Paste a direct PDF or arXiv link" aria-label="Paper URL" />
      <button type="button" disabled={busy || !paperUrl.trim()} onClick={() => onUrl(paperUrl.trim())}>Open</button>
    </span>
    {shownError && <span className="upload-error" role="alert">{shownError}</span>}
    <small>Text-based PDF · arXiv link</small>
  </div></div>;
}

const STATUS_TEXT: Record<HighlightStatus, string> = {
  searching: 'Locating the passage on the page…',
  quote: 'Highlighted on the page: the sentence PaperLens quoted from this passage.',
  'quote-approx': 'Highlighted on the page. The PDF text differs slightly from the extracted text, so the highlight may be a few words off.',
  'passage-start': 'This answer has no verified quote for this source, so the start of the cited passage is highlighted.',
  'not-found': 'The exact position was not found on this page. Read the extracted passage below.',
};

export function PaperViewer({ pdfUrl, focus, onCloseFocus }: { pdfUrl: string; focus: SourceFocus | null; onCloseFocus: () => void }) {
  const [target, setTarget] = useState<PdfTarget | null>(null);
  const [status, setStatus] = useState<HighlightStatus>('searching');
  const [showPassage, setShowPassage] = useState(false);
  const counter = useRef(0);
  // Every click on a source (even the same one again) creates a new target, so the viewer jumps back to it.
  useEffect(() => {
    if (!focus || focus.page == null) { setTarget(null); return; }
    counter.current += 1;
    setShowPassage(false);
    setStatus('searching');  // set before the viewer runs, so a quick result from the page is not overwritten
    setTarget({
      key: counter.current, page: focus.page, highlight: focus.kind === 'paper',
      quotes: focus.quotes ?? [], passage: focus.kind === 'paper' ? focus.text : null,
    });
  }, [focus]);
  const jumpTo = (page: number) => { counter.current += 1; setTarget({ key: counter.current, page, quotes: [], passage: null, highlight: false }); };
  const quotes = focus?.quotes ?? [];

  return <div className="paper-viewer">
    <PdfViewer url={pdfUrl} target={target} onStatus={setStatus} />
    {focus && <aside className="cited-passage" aria-label="Cited passage">
      <header>
        <span>{focus.label} · {pageText(focus)}</span>
        <button onClick={onCloseFocus} aria-label="Close cited passage"><X /></button>
      </header>
      {focus.kind === 'overview' ? <>
        <small>PaperLens-generated summary of these pages, not the authors’ words. Open a page to read the original text.</small>
        <p>{focus.text}</p>
        <div className="cited-pages">
          {(focus.pages?.length ? focus.pages : [focus.page ?? 1]).map((page) => <button key={page} onClick={() => jumpTo(page)}>PDF p. {page}</button>)}
        </div>
      </> : <>
        <small className={`highlight-status ${status}`} role="status">{STATUS_TEXT[status]}</small>
        {quotes.map((quote) => <blockquote key={quote}>“{quote}”</blockquote>)}
        {quotes.length > 0
          ? <button className="text-button" onClick={() => setShowPassage((v) => !v)}>
            {showPassage ? 'Hide the full passage' : 'Show the full passage'}</button>
          : null}
        {(showPassage || !quotes.length) && <p>{focus.text}</p>}
      </>}
    </aside>}
  </div>;
}

// Shown only when preparation fails, so the learner knows which part went wrong.
const FAILED_STAGE: Record<string, string> = {
  parsing: 'Failed while reading the text of the PDF.',
  indexing: 'Failed while building the search index.',
  summarizing: 'Failed while writing the overview of the paper.',
};

export function IndexingStatus({ paper, onRetry, onUploadAnother }: { paper: Paper; onRetry: () => void; onUploadAnother: () => void }) {
  if (paper.status !== 'failed') {
    return <div className="choice-screen indexing-status" aria-live="polite" aria-busy="true">
      <h1><LoaderCircle className="spin" aria-hidden="true" /> Preparing your paper…</h1>
      <p className="muted-text">Long papers can take a minute.</p>
    </div>;
  }
  return <div className="choice-screen indexing-status" aria-live="polite">
    <h1><AlertTriangle aria-hidden="true" /> This paper could not be prepared</h1>
    <div className="status-error" role="alert">
      {paper.failed_stage && FAILED_STAGE[paper.failed_stage] && <p><strong>{FAILED_STAGE[paper.failed_stage]}</strong></p>}
      <p>{paper.error}</p>
      <div className="form-actions">
        <button className="text-button" onClick={onUploadAnother}>Upload a different PDF</button>
        <button className="primary-button" onClick={onRetry}>Retry</button>
      </div>
    </div>
  </div>;
}
