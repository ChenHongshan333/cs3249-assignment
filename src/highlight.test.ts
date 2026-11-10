// Unit tests for locating cited sentences in PDF.js text items (run by `npm test`).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { locateOnPage, normalize } from './highlight.ts';

// How PDF.js typically splits a page: one item per line fragment, hyphenated line breaks, a ligature glyph.
const ITEMS = [
  'Our participant pool, skewed towards professionals and gradu-',
  'ate students in STEM-related ﬁelds, is not representative of the',
  'population at large. Future work should recruit more broadly.',
];

const covered = (items: string[], match: ReturnType<typeof locateOnPage>) =>
  match!.segments.map((s) => items[s.item].slice(s.start, s.end)).join('|');

test('normalize keeps only letters and digits and expands ligatures', () => {
  assert.equal(normalize('STEM-related ﬁelds, 2023!'), 'stemrelatedfields2023');
});

test('exact quote across line breaks and a hyphenated word', () => {
  const match = locateOnPage(ITEMS, ['graduate students in STEM-related fields, is not representative'], null);
  assert.equal(match?.kind, 'quote');
  assert.equal(covered(ITEMS, match), 'gradu|ate students in STEM-related ﬁelds, is not representative');
});

test('quote with a word dropped by the PDF extractor is still located approximately', () => {
  // backend text (pypdf) dropped the ligature: "felds"; PDF.js has "ﬁelds"
  const match = locateOnPage(ITEMS, ['Our participant pool, skewed towards professionals and graduate students in STEM-related felds, is not representative of the population at large.'], null);
  assert.equal(match?.kind, 'quote-approx');
  assert.ok(covered(ITEMS, match).startsWith('Our participant pool'));
  assert.ok(covered(ITEMS, match).endsWith('population at large'));
});

test('falls back to the start of the passage when there is no quote', () => {
  const match = locateOnPage(ITEMS, [], 'Our participant pool, skewed towards professionals and graduate students');
  assert.equal(match?.kind, 'passage-start');
  assert.equal(match?.segments[0].item, 0);
});

test('returns null instead of a wrong highlight', () => {
  assert.equal(locateOnPage(ITEMS, ['A sentence that is nowhere on this page at all.'], 'Completely different passage text that is not here.'), null);
  assert.equal(locateOnPage([], ['anything at all here'], null), null);
});
