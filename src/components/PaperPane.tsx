// Left pane (upload + PDF viewer) and the indexing status shown while a paper is processed.
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, FilePlus2, LoaderCircle, X } from 'lucide-react';
import type { Paper, Source } from '../api';
import { figureParts, sourceText, useT } from '../i18n';
import { type HighlightStatus, type PdfTarget, PdfViewer } from './PdfViewer';

/** A source the learner clicked; focusLabel is how it is named in the panel ("Source 2", "Note evidence"). */
export type SourceFocus = Source & { focusLabel: string };

export function LandingUpload({ onFile, onUrl, busy, error }: {
  onFile: (file: File) => void; onUrl: (url: string) => void; busy: boolean; error: string;
}) {
  const t = useT();
  const inputRef = useRef<HTMLInputElement>(null);
  const [paperUrl, setPaperUrl] = useState('');
  const [localError, setLocalError] = useState('');
  const acceptFile = (file?: File) => {
    if (!file || busy) return;
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setLocalError(t.notPdf);
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
      aria-label={t.chooseFile} onChange={(event) => { acceptFile(event.target.files?.[0]); event.target.value = ''; }} />
    {busy ? <LoaderCircle className="spin" aria-hidden="true" /> : <FilePlus2 aria-hidden="true" />}
    <span>{busy ? t.uploading : <>{t.dropHere[0]}<br />{t.dropHere[1]}</>}</span>
    <span className="url-field" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
      <input value={paperUrl} onChange={(event) => setPaperUrl(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Enter' && paperUrl.trim()) onUrl(paperUrl.trim()); }}
        placeholder={t.urlPlaceholder} aria-label={t.urlLabel} />
      <button type="button" disabled={busy || !paperUrl.trim()} onClick={() => onUrl(paperUrl.trim())}>{t.open}</button>
    </span>
    {shownError && <span className="upload-error" role="alert">{shownError}</span>}
    <small>{t.uploadHint}</small>
  </div></div>;
}

/**
 * PDF viewer plus a compact source bar. When the quote is highlighted exactly, the bar is a single line
 * (the highlight on the page says the rest). A second line appears only for approximate / missing positions.
 */
export function PaperViewer({ pdfUrl, focus, onCloseFocus }: { pdfUrl: string; focus: SourceFocus | null; onCloseFocus: () => void }) {
  const t = useT();
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
    if (focus.kind === 'figure') {
      // A figure: highlight the authors' caption (the description itself is not on the page).
      const caption = focus.caption ?? '';
      setTarget({ key: counter.current, page: focus.page, highlight: !!caption,
        quotes: focus.quotes?.length ? focus.quotes : caption ? [caption] : [], passage: null });
      return;
    }
    setTarget({
      key: counter.current, page: focus.page, highlight: focus.kind === 'paper',
      quotes: focus.quotes ?? [], passage: focus.kind === 'paper' ? focus.text : null,
    });
  }, [focus]);
  const jumpTo = (page: number) => { counter.current += 1; setTarget({ key: counter.current, page, quotes: [], passage: null, highlight: false }); };
  const overview = focus?.kind === 'overview';
  const figure = focus?.kind === 'figure' ? figureParts(focus) : null;
  const passageOpen = showPassage || status === 'not-found';
  const highlighted = focus?.kind === 'paper' || !!figure?.caption;
  const notice = highlighted && status !== 'quote' ? t.status[status] : '';

  return <div className="paper-viewer">
    <PdfViewer url={pdfUrl} target={target} onStatus={setStatus} />
    {focus && <aside className={`cited-passage ${overview ? 'overview' : 'compact'}`} aria-label={t.citedPassage}>
      <header>
        <span>{focus.focusLabel} · {sourceText(t, focus)}</span>
        {focus.kind === 'paper' && status !== 'not-found' && <button className="text-button" onClick={() => setShowPassage((v) => !v)}
          aria-expanded={passageOpen}>{passageOpen ? t.hidePassage : t.showPassage}</button>}
        <button className="close-button" onClick={onCloseFocus} aria-label={t.closePassage}><X /></button>
      </header>
      {notice && <small className={`highlight-status ${status}`} role="status">
        {status !== 'searching' && <AlertTriangle aria-hidden="true" />}{notice}</small>}
      {figure ? <>
        <small>{figure.caption ? t.figureNote : t.figureNoCaption}</small>
        <p>{figure.description}</p>
      </> : overview ? <>
        <small>{t.summaryNote}</small>
        <p>{focus.text}</p>
        <div className="cited-pages">
          {(focus.pages?.length ? focus.pages : [focus.page ?? 1]).map((page) => <button key={page} onClick={() => jumpTo(page)}>{t.pageButton(page)}</button>)}
        </div>
      </> : passageOpen && <p>{focus.text}</p>}
    </aside>}
  </div>;
}

export function IndexingStatus({ paper, onRetry, onUploadAnother }: { paper: Paper; onRetry: () => void; onUploadAnother: () => void }) {
  const t = useT();
  if (paper.status !== 'failed') {
    return <div className="choice-screen indexing-status" aria-live="polite" aria-busy="true">
      <h1><LoaderCircle className="spin" aria-hidden="true" /> {t.preparing}</h1>
      <p className="muted-text">{t.preparingHint}</p>
    </div>;
  }
  return <div className="choice-screen indexing-status" aria-live="polite">
    <h1><AlertTriangle aria-hidden="true" /> {t.prepFailed}</h1>
    <div className="status-error" role="alert">
      {/* the failed stage tells the learner which part went wrong; the error text itself comes from the backend */}
      {paper.failed_stage && t.failedStage[paper.failed_stage] && <p><strong>{t.failedStage[paper.failed_stage]}</strong></p>}
      <p>{paper.error}</p>
      <div className="form-actions">
        <button className="text-button" onClick={onUploadAnother}>{t.uploadDifferent}</button>
        <button className="primary-button" onClick={onRetry}>{t.retry}</button>
      </div>
    </div>
  </div>;
}
