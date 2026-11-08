// Locate a cited sentence inside the text items of a rendered PDF page (PDF.js text layer).
//
// The backend has already checked that each quote occurs in the stored passage text (pypdf extraction).
// PDF.js splits the same page into different text items and may differ in spacing, hyphenation or ligatures,
// so matching ignores everything except letters and digits, and falls back to anchoring on the start and end
// of the quote. No highlight is better than a wrong one: when nothing is found the caller says so.

export type Segment = { item: number; start: number; end: number }; // character offsets inside one text item (end exclusive)
export type MatchKind = 'quote' | 'quote-approx' | 'passage-start';
export type PageMatch = { kind: MatchKind; segments: Segment[] };

const WORD_CHAR = /[\p{L}\p{N}]/u;
const ANCHOR = 24;              // normalised characters (~4-5 words) used to anchor an approximate match
const PASSAGE_PREVIEW = 180;    // how much of a passage start to highlight when there is no verified quote

type Index = { text: string; pos: Array<{ item: number; offset: number }> };

/** Lower-case letters and digits only, after NFKC (so ligatures such as "ﬁ" become "fi"). */
export function normalize(value: string): string {
  let out = '';
  for (const ch of value.normalize('NFKC').toLowerCase()) if (WORD_CHAR.test(ch)) out += ch;
  return out;
}

function buildIndex(items: string[]): Index {
  let text = '';
  const pos: Index['pos'] = [];
  items.forEach((item, itemIndex) => {
    for (let offset = 0; offset < item.length; offset += 1) {
      for (const ch of item[offset].normalize('NFKC').toLowerCase()) {
        if (WORD_CHAR.test(ch)) { text += ch; pos.push({ item: itemIndex, offset }); }
      }
    }
  });
  return { text, pos };
}

/** Convert a range of the normalised text back into per-item character ranges. */
function toSegments(index: Index, from: number, to: number): Segment[] {
  const segments: Segment[] = [];
  for (let i = from; i < to && i < index.pos.length; i += 1) {
    const { item, offset } = index.pos[i];
    const last = segments[segments.length - 1];
    if (last && last.item === item) last.end = offset + 1;
    else segments.push({ item, start: offset, end: offset + 1 });
  }
  return segments;
}

function findQuote(index: Index, quote: string): { from: number; to: number; exact: boolean } | null {
  const needle = normalize(quote);
  if (needle.length < 12) return null;
  const exact = index.text.indexOf(needle);
  if (exact >= 0) return { from: exact, to: exact + needle.length, exact: true };
  if (needle.length < ANCHOR * 2) return null;
  const head = index.text.indexOf(needle.slice(0, ANCHOR));
  const tailNeedle = needle.slice(-ANCHOR);
  const tail = index.text.indexOf(tailNeedle, head >= 0 ? head : 0);
  if (head >= 0 && tail >= 0 && tail + ANCHOR - head <= needle.length * 1.5) return { from: head, to: tail + ANCHOR, exact: false };
  if (head >= 0) return { from: head, to: Math.min(head + needle.length, index.text.length), exact: false };
  if (tail >= 0) return { from: Math.max(0, tail + ANCHOR - needle.length), to: tail + ANCHOR, exact: false };
  return null;
}

function findPassageStart(index: Index, passage: string): { from: number; to: number } | null {
  const needle = normalize(passage);
  for (const offset of [0, 40, 80, 120]) {
    const anchor = needle.slice(offset, offset + ANCHOR);
    if (anchor.length < ANCHOR) break;
    const found = index.text.indexOf(anchor);
    if (found >= 0) {
      const from = Math.max(0, found - offset);
      return { from, to: Math.min(from + Math.min(needle.length, PASSAGE_PREVIEW), index.text.length) };
    }
  }
  return null;
}

/**
 * Find what to highlight on one page.
 * 1. every verified quote (exact match, else anchored on its first/last words);
 * 2. otherwise the start of the cited passage (older answers have no quotes);
 * 3. otherwise null: the caller tells the learner the position was not found.
 */
export function locateOnPage(items: string[], quotes: string[], passage: string | null): PageMatch | null {
  const index = buildIndex(items);
  if (!index.text) return null;
  const hits = quotes.map((quote) => findQuote(index, quote)).filter((hit): hit is NonNullable<typeof hit> => hit !== null);
  if (hits.length) {
    hits.sort((a, b) => a.from - b.from);
    return {
      kind: hits.every((hit) => hit.exact) ? 'quote' : 'quote-approx',
      segments: hits.flatMap((hit) => toSegments(index, hit.from, hit.to)),
    };
  }
  const start = passage ? findPassageStart(index, passage) : null;
  return start ? { kind: 'passage-start', segments: toSegments(index, start.from, start.to) } : null;
}
