// PDF viewer built on PDF.js: continuous pages, lazy rendering, a text layer per page, and highlighting of the
// cited sentence on the page (see src/highlight.ts). Replaces the browser's built-in viewer (an <iframe>), which
// a web page cannot draw highlights into.
import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Download, ExternalLink, ZoomIn, ZoomOut } from 'lucide-react';
import { getDocument, GlobalWorkerOptions, TextLayer, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import { locateOnPage, type MatchKind } from '../highlight';

GlobalWorkerOptions.workerSrc = workerUrl;

export type HighlightStatus = 'searching' | MatchKind | 'not-found';
/** A request to show a page; with quotes/passage it also highlights them. `key` changes on every click. */
export type PdfTarget = { key: number; page: number; quotes: string[]; passage: string | null; highlight: boolean };

type PageSize = { width: number; height: number };
type Rect = { left: number; top: number; width: number; height: number }; // percentages of the page box

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const PAGE_GAP = 14;

function PdfPage({ doc, pageNumber, size, scale, active, target, onHighlight, register }: {
  doc: PDFDocumentProxy; pageNumber: number; size: PageSize; scale: number; active: boolean;
  target: PdfTarget | null; onHighlight: (target: PdfTarget, status: HighlightStatus, topPx: number) => void;
  register: (pageNumber: number, node: HTMLDivElement | null) => void;
}) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const textDivs = useRef<HTMLElement[]>([]);
  const renderedScale = useRef<number | null>(null);
  const [textVersion, setTextVersion] = useState(0);
  const [rects, setRects] = useState<Rect[]>([]);

  // Render the canvas and the text layer when the page is (nearly) visible or the zoom changes.
  useEffect(() => {
    if (!active || renderedScale.current === scale) return undefined;
    let cancelled = false;
    let task: RenderTask | null = null;
    let textLayer: TextLayer | null = null;
    (async () => {
      const page = await doc.getPage(pageNumber);
      if (cancelled || !canvasRef.current || !textRef.current) return;
      const viewport = page.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      const canvas = canvasRef.current;
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      const context = canvas.getContext('2d');
      if (!context) return;
      task = page.render({ canvasContext: context, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] });
      await task.promise;
      if (cancelled) return;
      textRef.current.replaceChildren();
      textLayer = new TextLayer({ textContentSource: page.streamTextContent(), container: textRef.current, viewport });
      await textLayer.render();
      if (cancelled) return;
      textDivs.current = textLayer.textDivs;
      renderedScale.current = scale;
      setTextVersion((v) => v + 1);
    })().catch((error: unknown) => {
      if ((error as { name?: string })?.name !== 'RenderingCancelledException') console.warn(`PDF page ${pageNumber}:`, error);
    });
    return () => { cancelled = true; task?.cancel(); textLayer?.cancel(); };
  }, [active, doc, pageNumber, scale]);

  // Locate the cited sentence in this page's text layer and draw highlight boxes over it.
  const mine = target && target.highlight && target.page === pageNumber ? target : null;
  useEffect(() => {
    if (!mine) { setRects([]); return; }
    if (!textVersion || !boxRef.current) return;
    const items = textDivs.current.map((div) => div.textContent ?? '');
    const match = locateOnPage(items, mine.quotes, mine.passage);
    if (!match) { setRects([]); onHighlight(mine, 'not-found', 0); return; }
    const box = boxRef.current.getBoundingClientRect();
    const next: Rect[] = [];
    for (const segment of match.segments) {
      const node = textDivs.current[segment.item]?.firstChild;
      if (!node || node.nodeType !== Node.TEXT_NODE) continue;
      const range = document.createRange();
      range.setStart(node, Math.min(segment.start, node.textContent!.length));
      range.setEnd(node, Math.min(segment.end, node.textContent!.length));
      for (const r of Array.from(range.getClientRects())) {
        if (r.width < 1 || r.height < 1) continue;
        next.push({
          left: ((r.left - box.left) / box.width) * 100, top: ((r.top - box.top) / box.height) * 100,
          width: (r.width / box.width) * 100, height: (r.height / box.height) * 100,
        });
      }
    }
    setRects(next);
    const top = next.length ? Math.min(...next.map((r) => r.top)) : 0;
    onHighlight(mine, next.length ? match.kind : 'not-found', (top / 100) * box.height);
  }, [mine, textVersion, onHighlight]);

  return <div className="pdf-page" data-page={pageNumber}
    ref={(node) => { boxRef.current = node; register(pageNumber, node); }}
    style={{ width: size.width * scale, height: size.height * scale, '--scale-factor': scale, '--user-unit': 1 } as CSSProperties}>
    <canvas ref={canvasRef} aria-hidden="true" />
    <div className="pdf-highlights" aria-hidden="true">
      {rects.map((r, i) => <span key={i} style={{ left: `${r.left}%`, top: `${r.top}%`, width: `${r.width}%`, height: `${r.height}%` }} />)}
    </div>
    <div ref={textRef} className="textLayer" />
  </div>;
}

export function PdfViewer({ url, target, onStatus }: {
  url: string; target: PdfTarget | null; onStatus: (status: HighlightStatus) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pageNodes = useRef(new Map<number, HTMLDivElement>());
  const scrolledFor = useRef<number | null>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [sizes, setSizes] = useState<PageSize[]>([]);
  const [error, setError] = useState('');
  const [availableWidth, setAvailableWidth] = useState(0);
  const [zoom, setZoom] = useState<number | 'fit'>('fit');
  const [visible, setVisible] = useState<Set<number>>(new Set([1]));
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState('1');

  // Load the document and every page's size (needed to lay out placeholders before rendering).
  useEffect(() => {
    setDoc(null); setSizes([]); setError(''); setVisible(new Set([1])); setCurrentPage(1); setPageInput('1');
    const task = getDocument({ url });
    let cancelled = false;
    task.promise.then(async (loaded) => {
      const pageSizes = await Promise.all(Array.from({ length: loaded.numPages }, (_, i) => loaded.getPage(i + 1).then((page) => {
        const viewport = page.getViewport({ scale: 1 });
        return { width: viewport.width, height: viewport.height };
      })));
      if (!cancelled) { setSizes(pageSizes); setDoc(loaded); }
    }).catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; void task.destroy(); };
  }, [url]);

  // Fit-to-width follows the pane width (the splitter can resize it).
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return undefined;
    const observer = new ResizeObserver(() => setAvailableWidth(node.clientWidth));
    observer.observe(node);
    setAvailableWidth(node.clientWidth);
    return () => observer.disconnect();
  }, [doc]);
  const widest = sizes.reduce((max, s) => Math.max(max, s.width), 0) || 612;
  const fitScale = availableWidth ? Math.max(MIN_ZOOM, (availableWidth - 2 * PAGE_GAP) / widest) : 1;
  const scale = zoom === 'fit' ? fitScale : zoom;

  // Render only pages near the viewport.
  const register = useCallback((pageNumber: number, node: HTMLDivElement | null) => {
    if (node) pageNodes.current.set(pageNumber, node); else pageNodes.current.delete(pageNumber);
  }, []);
  useEffect(() => {
    const root = scrollRef.current;
    if (!root || !doc) return undefined;
    const observer = new IntersectionObserver((entries) => {
      setVisible((previous) => {
        const next = new Set(previous);
        for (const entry of entries) {
          const page = Number((entry.target as HTMLElement).dataset.page);
          if (entry.isIntersecting) next.add(page); else next.delete(page);
        }
        return next;
      });
    }, { root, rootMargin: '900px 0px' });
    pageNodes.current.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [doc, sizes]);

  const scrollToPage = useCallback((page: number, offsetPx = 0, smooth = false) => {
    const node = pageNodes.current.get(page);
    const root = scrollRef.current;
    if (!node || !root) return;
    root.scrollTo({ top: Math.max(0, node.offsetTop + offsetPx - (offsetPx ? root.clientHeight * 0.3 : PAGE_GAP)), behavior: smooth ? 'smooth' : 'auto' });
  }, []);

  // A new target: jump to its page; the page reports back once the highlight is placed. React runs the page's
  // effects before this one, so if the page was already rendered the highlight may already have scrolled
  // into view — then do not jump back to the top of the page.
  useEffect(() => {
    if (!target || !doc || scrolledFor.current === target.key) return;
    scrollToPage(Math.min(Math.max(1, target.page), doc.numPages));
  }, [target, doc, scrollToPage]);
  const onHighlight = useCallback((forTarget: PdfTarget, status: HighlightStatus, topPx: number) => {
    onStatus(status);
    if (status !== 'not-found' && scrolledFor.current !== forTarget.key) {
      scrolledFor.current = forTarget.key;
      scrollToPage(forTarget.page, topPx, true);
    }
  }, [onStatus, scrollToPage]);

  const onScroll = () => {
    const root = scrollRef.current;
    if (!root) return;
    const probe = root.scrollTop + root.clientHeight / 3;
    let page = 1;
    pageNodes.current.forEach((node, number) => { if (node.offsetTop <= probe && number > page) page = number; });
    if (page !== currentPage) { setCurrentPage(page); setPageInput(String(page)); }
  };
  const goTo = (page: number) => {
    if (!doc) return;
    const clamped = Math.min(Math.max(1, page), doc.numPages);
    setPageInput(String(clamped));
    scrollToPage(clamped);
  };
  const changeZoom = (factor: number) => setZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(scale * factor * 100) / 100)));

  return <div className="pdf-viewer">
    <div className="pdf-toolbar" role="toolbar" aria-label="PDF controls">
      <button onClick={() => goTo(currentPage - 1)} disabled={!doc || currentPage <= 1} aria-label="Previous page"><ChevronLeft /></button>
      <form onSubmit={(event) => { event.preventDefault(); goTo(Number(pageInput) || currentPage); }}>
        <input value={pageInput} onChange={(event) => setPageInput(event.target.value.replace(/\D/g, ''))} aria-label="Page number" inputMode="numeric" />
        <span>/ {doc?.numPages ?? '–'}</span>
      </form>
      <button onClick={() => goTo(currentPage + 1)} disabled={!doc || currentPage >= (doc?.numPages ?? 1)} aria-label="Next page"><ChevronRight /></button>
      <span className="pdf-toolbar-divider" />
      <button onClick={() => changeZoom(1 / 1.2)} disabled={!doc || scale <= MIN_ZOOM} aria-label="Zoom out"><ZoomOut /></button>
      <button className={`pdf-zoom-label ${zoom === 'fit' ? 'active' : ''}`} onClick={() => setZoom('fit')} disabled={!doc}
        title="Fit to width">{zoom === 'fit' ? 'Fit' : `${Math.round(scale * 100)}%`}</button>
      <button onClick={() => changeZoom(1.2)} disabled={!doc || scale >= MAX_ZOOM} aria-label="Zoom in"><ZoomIn /></button>
      <span className="pdf-toolbar-spacer" />
      <a href={`${url}#page=${currentPage}`} target="_blank" rel="noreferrer" aria-label="Open in the browser's PDF viewer" title="Open in the browser's PDF viewer (search, print)"><ExternalLink /></a>
      <a href={url} download aria-label="Download PDF" title="Download PDF"><Download /></a>
    </div>
    <div className="pdf-scroll" ref={scrollRef} onScroll={onScroll}>
      {error && <p className="pdf-error" role="alert">This PDF could not be displayed here ({error}). <a href={url} target="_blank" rel="noreferrer">Open it in the browser's viewer</a>.</p>}
      {!doc && !error && <p className="pdf-loading">Loading PDF…</p>}
      {doc && <div className="pdf-pages" style={{ gap: PAGE_GAP, padding: PAGE_GAP }}>
        {sizes.map((size, index) => <PdfPage key={index + 1} doc={doc} pageNumber={index + 1} size={size} scale={scale}
          active={visible.has(index + 1) || target?.page === index + 1} target={target} onHighlight={onHighlight} register={register} />)}
      </div>}
    </div>
  </div>;
}
