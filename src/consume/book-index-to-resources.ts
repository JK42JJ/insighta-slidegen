import type { BookIndex } from '@/consume/book-index';
import type { PlannedSegment } from '@/consume/consume-book-index';
import type {
  ChartResource,
  FormulaResource,
  OrchestrateResources,
} from '@/deck/orchestrate-runner';

const EQUATION_KIND = 'equation';

/**
 * ⑥ input side: map a consumed mandala book-index into the OrchestrateResources
 * bundle the vendored deck builder renders into a .pptx. The visible deck =
 * `runOrchestrate(resources, llm)` (NOT the SlideOutline — that is a separate,
 * DB-persisted deterministic outline).
 *
 * Path2 (text-only) is the floor: segments carry the section text so a deck is
 * produced even with ZERO figures (stub ⑤). Path1 figures contribute formulas
 * (equation LaTeX — the one struct FigureRef carries).
 *
 * NOTE / backlog: chart|diagram|table figures must be regenerated from their
 * CV struct to be placed, but FigureRef does not carry struct — so `charts`
 * stays empty until the insighta ⑤ contract returns struct/resources. Never
 * fabricate a struct (fail-closed): an unplaceable figure is simply omitted,
 * the deck still renders its text.
 */
export function bookIndexToResources(
  book: BookIndex,
  planned: PlannedSegment[]
): OrchestrateResources {
  const segments = planned.map((p, index) => ({
    index,
    from_sec: p.segment.from_sec,
    to_sec: p.segment.to_sec,
    title: p.segment.title,
    summary: p.segment.text,
  }));

  const formulas: FormulaResource[] = [];
  for (const p of planned) {
    for (const fig of p.figures) {
      if (fig.kind === EQUATION_KIND && fig.extracted_latex) {
        formulas.push({
          figure_id: fig.cv_figure_id,
          latex: fig.extracted_latex,
          conf: fig.extraction_conf,
          t: fig.timestamp_sec,
          verification_status: fig.verification_status,
        });
      }
    }
  }

  // charts[]: struct-bearing figures need the CV struct to regenerate; FigureRef
  // carries none → empty until ⑤ returns struct/resources (backlog). No fabrication.
  const charts: ChartResource[] = [];

  const transcript = planned
    .map((p) => p.segment.text)
    .filter((text) => text.length > 0)
    .join('\n\n');

  return {
    title: book.center_goal,
    transcript,
    segments,
    figureLabels: [],
    formulas,
    charts,
  };
}
