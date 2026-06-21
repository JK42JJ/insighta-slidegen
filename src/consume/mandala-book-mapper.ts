import { BookIndexSchema, type BookIndex, type BookIndexSegment } from '@/consume/book-index';

/**
 * Map an insighta `mandala_books.book_json` (read-only upstream, owned by
 * insighta ③) into the slidegen `BookIndex` the ④ consumer reads.
 *
 * book_json shape reconciled from prod (mandala aa3092ca, version 1, 2026-06-22):
 *   { mandala_title, mandala_id, schema_version, source_videos, source_atoms,
 *     chapters[] { ch, title, intro,
 *       sections[] { title, narrative, qa[],
 *         atoms[] { vid (11-char yt id), type, seg_ref, text, ts (number) } } } }
 *
 * Fail-closed: a section without an 11-char source `vid` or with empty narrative
 * is SKIPPED — never fabricated. has_visual_structure is false here (text-only:
 * the figure/object branch is gated by ⑤; this mapper feeds the Path2 floor).
 * Real per-(video,mandala) relevance lives in `video_mandala_segment_relevance`
 * (②) — wired in the real path; under the stub ⑤ the gate is moot (all Path2),
 * so a neutral relevance is used here.
 */

interface MandalaAtom {
  vid?: unknown;
  ts?: unknown;
}
interface MandalaSection {
  title?: unknown;
  narrative?: unknown;
  atoms?: unknown;
}
interface MandalaChapter {
  title?: unknown;
  sections?: unknown;
}
interface MandalaBookJson {
  mandala_title?: unknown;
  mandala_id?: unknown;
  chapters?: unknown;
}

const YT_ID_LEN = 11;
/** Neutral relevance: the gate is moot under the stub ⑤ (all Path2); the real
 * path reads video_mandala_segment_relevance (②). Not a magic threshold. */
const NEUTRAL_RELEVANCE_PCT = 100;

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function mapMandalaBookJson(raw: unknown): BookIndex {
  const book = (raw ?? {}) as MandalaBookJson;
  const segments: BookIndexSegment[] = [];

  for (const chRaw of asArray(book.chapters)) {
    const ch = chRaw as MandalaChapter;
    for (const secRaw of asArray(ch.sections)) {
      const sec = secRaw as MandalaSection;
      const atoms = asArray(sec.atoms) as MandalaAtom[];

      const vid = atoms.map((a) => asString(a.vid)).find((v) => v.length === YT_ID_LEN);
      const text = asString(sec.narrative).trim();
      if (!vid || !text) continue; // fail-closed: no source video / no body → skip

      const tsList = atoms.map((a) => a.ts).filter((t): t is number => typeof t === 'number');
      const fromSec = tsList.length ? Math.min(...tsList) : 0;
      const toSec = tsList.length ? Math.max(...tsList) : fromSec;

      segments.push({
        video_id: vid,
        from_sec: fromSec,
        to_sec: toSec,
        title: asString(sec.title).trim() || asString(ch.title).trim() || 'Untitled',
        text,
        relevance_pct: NEUTRAL_RELEVANCE_PCT,
        has_visual_structure: false,
      });
    }
  }

  return BookIndexSchema.parse({
    mandala_id: asString(book.mandala_id) || 'unknown',
    center_goal: asString(book.mandala_title).trim() || 'Untitled mandala',
    segments,
  });
}
