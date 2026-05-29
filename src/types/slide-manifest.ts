/**
 * Zod schemas and inferred TypeScript types for the slidegen pipeline.
 * All inter-module contracts use these types; no ad-hoc inline types.
 */
import { z } from 'zod';

// ----------------------------------------------------------------
// V2 Summary mirror (fail-loud validation at fetch time)
// ----------------------------------------------------------------

const V2AtomSchema = z.object({
  type: z.string(),
  text: z.string(),
  timestamp_sec: z.number().nullable().optional(),
  entity_refs: z.array(z.string()).optional(),
});

const V2EntitySchema = z.object({
  name: z.string(),
  type: z.string(),
});

const V2SectionSchema = z.object({
  from_sec: z.number(),
  to_sec: z.number(),
  title: z.string(),
  summary: z.string(),
  relevance_pct: z.number().min(0).max(100),
  key_points: z.array(z.string()),
});

const V2CoreSchema = z.object({
  title: z.string().optional(),
  one_liner: z.string().optional(),
  key_concepts: z.array(z.string()).optional(),
  qa_pairs: z.array(z.object({ q: z.string(), a: z.string() })).optional(),
});

const V2AnalysisSchema = z.object({
  atoms: z.array(V2AtomSchema).optional(),
  entities: z.array(V2EntitySchema).optional(),
});

/** Zod mirror of the v2 video_rich_summaries row consumed by slidegen. */
export const V2SummarySchema = z.object({
  video_id: z.string().length(11),
  template_version: z.literal('v2'),
  source_language: z.string().nullable().optional(),
  quality_flag: z.literal('pass'),
  transcript_used: z.literal(true),
  core: V2CoreSchema.nullable().optional(),
  analysis: V2AnalysisSchema.nullable().optional(),
  segments: z.array(V2SectionSchema).nullable().optional(),
  lora: z.unknown().nullable().optional(),
  mandala_relevance_pct: z.number().nullable().optional(),
});

export type V2Summary = z.infer<typeof V2SummarySchema>;
export type V2Section = z.infer<typeof V2SectionSchema>;
export type V2Atom = z.infer<typeof V2AtomSchema>;
export type V2Entity = z.infer<typeof V2EntitySchema>;

// ----------------------------------------------------------------
// Slide layouts
// ----------------------------------------------------------------

/** Available layout identifiers — must match templates.ts LAYOUT_MAP keys. */
export const LayoutEnum = z.enum([
  'cover',
  'section_intro',
  'key_points',
  'qa_pair',
  'figure_full',
  'figure_caption',
  'timeline',
  'summary',
  'blank',
]);

export type Layout = z.infer<typeof LayoutEnum>;

// ----------------------------------------------------------------
// FigureRef — CV service → slidegen contract
// ----------------------------------------------------------------

/** A figure produced by the CV service, ready to embed in a slide. */
export const FigureRefSchema = z.object({
  cv_figure_id: z.string(),
  kind: z.enum(['chart', 'diagram', 'equation', 'table', 'screenshot', 'keyframe']),
  png_url: z.string().url(),
  vector_pdf_url: z.string().url().optional(),
  vector_svg_url: z.string().url().optional(),
  caption: z.string().optional(),
  timestamp_sec: z.number().int().optional(),
  atom_refs: z.array(z.number().int()).optional(),
  extraction_conf: z.number().min(0).max(1).optional(),
});

export type FigureRef = z.infer<typeof FigureRefSchema>;

// ----------------------------------------------------------------
// SlideOutline — planner output, builder input
// ----------------------------------------------------------------

/** A single planned slide before Google Slides objects are created. */
export const SlideSchema = z.object({
  position: z.number().int(),
  layout: LayoutEnum,
  title: z.string().optional(),
  body_json: z.unknown().optional(),
  notes: z.string().optional(),
  section_ref: z.number().int().optional(),
  figures: z.array(FigureRefSchema).optional(),
});

export type Slide = z.infer<typeof SlideSchema>;

/** Full deck outline produced by the slide planner. */
export const SlideOutlineSchema = z.object({
  video_id: z.string().length(11),
  lang: z.string(),
  generator_version: z.string(),
  v2_fingerprint: z.string(),
  slides: z.array(SlideSchema),
});

export type SlideOutline = z.infer<typeof SlideOutlineSchema>;
