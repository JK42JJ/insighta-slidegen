/**
 * Layout enum and field-map definitions for slide templates.
 * All layout identifiers referenced here must match LayoutEnum in slide-manifest.ts.
 *
 * A LayoutFieldMap describes which v2 fields populate which template zones.
 * The planner (slide-planner.ts) reads these maps to build body_json for each slide.
 */
import { type Layout } from '@/types/slide-manifest';

/** Zones available in a slide template. Not every layout uses all zones. */
export interface TemplateZone {
  /** Title zone (top bar) */
  title?: string;
  /** Primary body zone — bullet list, paragraph, or figure placeholder */
  body?: string;
  /** Secondary body / right-column zone */
  body2?: string;
  /** Speaker notes zone */
  notes?: string;
  /** Aspect ratio for figure slots: "16:9" | "4:3" | "1:1" */
  figureAspect?: '16:9' | '4:3' | '1:1';
}

/** Maps each layout to which v2 source fields fill its zones. */
export interface LayoutFieldMap {
  layout: Layout;
  zones: TemplateZone;
  /** v2 field path that provides primary content (dot-notation). */
  primarySource: string;
  /** Maximum number of bullet points / items rendered in body zone. */
  maxItems?: number;
}

/**
 * Master layout field map.
 *
 * Source paths follow the REAL v2 shape (slide-manifest.ts mirror):
 *   - sections live at `segments.sections[n]` (segments is an object);
 *   - key_points entries are `{ text, timestamp_sec? }` objects → render `.text`;
 *   - there is NO core.title / core.qa_pairs — cover titles from core.one_liner
 *     and the per-insight layout ('atom_highlight', formerly 'qa_pair')
 *     sources from `segments.atoms[n]`;
 *   - key concepts live at `analysis.key_concepts` ({ term, definition }[]).
 *
 * TODO: refine zone wiring per UX spec; current values document the v2 source
 * of truth for each zone.
 */
export const LAYOUT_MAP: Record<Layout, LayoutFieldMap> = {
  cover: {
    layout: 'cover',
    primarySource: 'core.one_liner',
    zones: { title: 'core.one_liner', body: 'analysis.core_argument' },
  },
  section_intro: {
    layout: 'section_intro',
    primarySource: 'segments.sections[n].title',
    zones: { title: 'segments.sections[n].title', body: 'segments.sections[n].summary' },
  },
  key_points: {
    layout: 'key_points',
    primarySource: 'segments.sections[n].key_points',
    zones: {
      title: 'segments.sections[n].title',
      body: 'segments.sections[n].key_points[*].text',
    },
    maxItems: 5,
  },
  atom_highlight: {
    layout: 'atom_highlight',
    primarySource: 'segments.atoms[n]',
    zones: { title: 'segments.atoms[n].type', body: 'segments.atoms[n].text' },
  },
  figure_full: {
    layout: 'figure_full',
    primarySource: 'cv_figure',
    zones: { title: 'figure.caption', figureAspect: '16:9' },
  },
  figure_caption: {
    layout: 'figure_caption',
    primarySource: 'cv_figure',
    zones: {
      title: 'figure.caption',
      body: 'figure.caption',
      figureAspect: '4:3',
    },
  },
  timeline: {
    layout: 'timeline',
    primarySource: 'segments.sections',
    zones: { title: 'core.one_liner', body: 'segments.sections[*].title' },
  },
  summary: {
    layout: 'summary',
    primarySource: 'analysis.key_concepts',
    zones: { title: 'core.one_liner', body: 'analysis.key_concepts[*].term' },
    maxItems: 6,
  },
  blank: {
    layout: 'blank',
    primarySource: '',
    zones: {},
  },
};
