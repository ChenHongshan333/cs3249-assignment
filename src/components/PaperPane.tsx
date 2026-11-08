// Left pane (upload + PDF viewer) and the indexing status shown while a paper is processed.
import { useRef, useState } from 'react';
import { AlertTriangle, Check, FilePlus2, LoaderCircle, X } from 'lucide-react';
import { pageText, type Paper, type Source } from '../api';

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

export function PaperViewer({ pdfUrl, focus, onCloseFocus }: { pdfUrl: string; focus: SourceFocus | null; onCloseFocus: () => void }) {
  const page = focus?.page ?? 1;
  return <div className="paper-viewer local-pdf-viewer">
    {/* Re-keying the iframe makes the browser's PDF viewer jump to the requested page. */}
    <iframe key={`${pdfUrl}-${page}-${focus?.ref_id ?? ''}`} className="local-pdf-frame"
      src={`${pdfUrl}#page=${page}&view=FitH`} title="Paper PDF" />
    {focus && <aside className="cited-passage" aria-label="Cited passage">
      <header>
        <span>{focus.label} · {pageText(focus)}</span>
        <button onClick={onCloseFocus} aria-label="Close cited passage"><X /></button>
      </header>
      <small>{focus.kind === 'overview'
        ? 'PaperLens-generated summary of these pages (not the authors’ words)'
        : 'Extracted text of the cited passage on this page (position on the page is not highlighted)'}</small>
      <p>{focus.text}</p>
    </aside>}
  </div>;
}

const STEPS: { key: Paper['status']; label: string }[] = [
  { key: 'parsing', label: 'Extracting text from each page' },
  { key: 'indexing', label: 'Splitting into passages and building the search index' },
  { key: 'summarizing', label: 'Writing a sourced overview of the whole paper' },
  { key: 'ready', label: 'Ready' },
];

export function IndexingStatus({ paper, onRetry, onUploadAnother }: { paper: Paper; onRetry: () => void; onUploadAnother: () => void }) {
  const failedIndex = paper.status === 'failed' ? STEPS.findIndex((s) => s.key === paper.failed_stage) : -1;
  const current = paper.status === 'failed' ? failedIndex : STEPS.findIndex((s) => s.key === paper.status);
  return <div className="choice-screen indexing-status" aria-live="polite">
    <h1>{paper.status === 'failed' ? 'This paper could not be prepared' : 'Preparing your paper…'}</h1>
    <ol className="status-steps">
      {STEPS.map((step, index) => {
        const state = paper.status === 'failed' && index === failedIndex ? 'failed'
          : index < current || paper.status === 'ready' ? 'done' : index === current ? 'active' : 'pending';
        return <li key={step.key} className={state}>
          {state === 'done' ? <Check /> : state === 'failed' ? <AlertTriangle /> : state === 'active' ? <LoaderCircle className="spin" /> : <span className="dot" />}
          {step.label}
        </li>;
      })}
    </ol>
    {paper.status === 'failed' && <div className="status-error" role="alert">
      <p>{paper.error}</p>
      <div className="form-actions">
        <button className="text-button" onClick={onUploadAnother}>Upload a different PDF</button>
        <button className="primary-button" onClick={onRetry}>Retry</button>
      </div>
    </div>}
  </div>;
}
