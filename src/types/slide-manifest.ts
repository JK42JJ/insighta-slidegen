/**
 * Zod schemas and inferred TypeScript types for the slidegen pipeline.
 * All inter-module contracts use these types; no ad-hoc inline types.
 */
import { z } from 'zod';

// ----------------------------------------------------------------
// V2 Summary mirror (fail-loud validation at fetch time)
//
// Source of truth: parent insighta repo,
// `src/modules/skills/rich-summary-v2-prompt.ts` (RichSummaryV2Layered).
// Real layered row shape (jsonb columns on video_rich_summaries):
//   core     — { one_liner, domain, depth_level, content_type, target_audience }
//   analysis — { core_argument, key_concepts, entities, actionables,
//                mandala_fit, bias_signals, prerequisites }
//   lora     — { qa_pairs } (NOT consumed by slidegen — kept opaque)
//   segments — OBJECT { sections: [...], atoms: [...] } (optional/null;
//              NOT an array; CP474 — absent when transcript was missing)
//
// Mirror policy: strictly type ONLY what slidegen consumes
// (core fields, segments.sections, segments.atoms, analysis.entities,
// analysis.key_concepts) and keep everything else lenient
// (.passthrough() / z.unknown() / optional) so every REAL v2 row parses.
// Fail-loud is reserved for the gate fields (video_id / template_version /
// quality_flag / transcript_used) and shape violations on consumed fields
// (e.g. segments delivered as an array must throw).
// ----------------------------------------------------------------

/** segments.sections[i].key_points[j] — { text, timestamp_sec? } objects, NOT bare strings. */
export const V2KeyPointSchema = z
  .object({
    text: z.string(),
    timestamp_sec: z.number().nullable().optional(),
  })
  .passthrough();

/**
 * segments.sections[i]. `relevance_pct` is documented 0-100 upstream but
 * only key-whitelisted (not range-validated) at write time, so the mirror
 * accepts any number rather than rejecting real rows.
 */
export const V2SectionSchema = z
  .object({
    idx: z.number().nullable().optional(),
    from_sec: z.number(),
    to_sec: z.number(),
    title: z.string(),
    summary: z.string().nullable().optional(),
    relevance_pct: z.number(),
    key_points: z.array(V2KeyPointSchema).nullable().optional(),
  })
  .passthrough();

/**
 * segments.atoms[i]. `type` vocabulary per the upstream prompt is
 * 'fact' | 'argument' | 'tip' | 'other', but the upstream validator only
 * whitelists KEYS (RichSummaryAtom.type is `string`) — kept as z.string()
 * so real rows never fail; consumers filter by exact value.
 */
export const V2AtomSchema = z
  .object({
    idx: z.number().nullable().optional(),
    type: z.string(),
    text: z.string(),
    timestamp_sec: z.number().nullable().optional(),
    entity_refs: z.array(z.string()).nullable().optional(),
  })
  .passthrough();

/** segments column — an OBJECT wrapper, never an array. Both keys optional. */
export const V2SegmentsSchema = z
  .object({
    sections: z.array(V2SectionSchema).nullable().optional(),
    atoms: z.array(V2AtomSchema).nullable().optional(),
  })
  .passthrough();

/**
 * analysis.entities[i]. Upstream `type` vocabulary:
 * 'concept' | 'person' | 'tool' | 'framework' | 'organization'
 * (validated upstream; mirrored leniently as string).
 */
export const V2EntitySchema = z
  .object({
    name: z.string(),
    type: z.string(),
  })
  .passthrough();

/**
 * core column — all five fields are guaranteed non-empty strings on a
 * quality_flag='pass' row (validateV2Layered upstream). There is NO
 * core.title and NO core.qa_pairs in the real shape.
 */
export const V2CoreSchema = z
  .object({
    one_liner: z.string(),
    domain: z.string(),
    depth_level: z.string(),
    content_type: z.string(),
    target_audience: z.string(),
  })
  .passthrough();

/**
 * analysis column. Atoms are NOT here (they live in segments.atoms).
 * Only the fields slidegen consumes are typed; actionables / mandala_fit /
 * bias_signals / prerequisites pass through untyped.
 */
export const V2AnalysisSchema = z
  .object({
    core_argument: z.string().optional(),
    key_concepts: z
      .array(z.object({ term: z.string(), definition: z.string() }).passthrough())
      .nullable()
      .optional(),
    entities: z.array(V2EntitySchema).nullable().optional(),
  })
  .passthrough();

/** Zod mirror of the v2 video_rich_summaries row consumed by slidegen. */
export const V2SummarySchema = z.object({
  video_id: z.string().length(11),
  template_version: z.literal('v2'),
  source_language: z.string().nullable().optional(),
  quality_flag: z.literal('pass'),
  transcript_used: z.literal(true),
  core: V2CoreSchema,
  analysis: V2AnalysisSchema,
  segments: V2SegmentsSchema.nullable().optional(),
  lora: z.unknown().nullable().optional(),
  mandala_relevance_pct: z.number().nullable().optional(),
});

export type V2Summary = z.infer<typeof V2SummarySchema>;
export type V2Segments = z.infer<typeof V2SegmentsSchema>;
export type V2Section = z.infer<typeof V2SectionSchema>;
export type V2KeyPoint = z.infer<typeof V2KeyPointSchema>;
export type V2Atom = z.infer<typeof V2AtomSchema>;
export type V2Entity = z.infer<typeof V2EntitySchema>;
export type V2Core = z.infer<typeof V2CoreSchema>;
export type V2Analysis = z.infer<typeof V2AnalysisSchema>;

// ----------------------------------------------------------------
// Slide layouts
// ----------------------------------------------------------------

/**
 * Available layout identifiers — must match templates.ts LAYOUT_MAP keys.
 * 'atom_highlight' replaces the former 'qa_pair' layout: the real v2 shape
 * has no core.qa_pairs, so the per-insight slide sources from segments.atoms.
 */
export const LayoutEnum = z.enum([
  'cover',
  'section_intro',
  'key_points',
  'atom_highlight',
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

/** YOLO crop region in source-frame pixels (slide_figures.bbox shape, PR-F3). */
export const FigureBboxSchema = z.object({
  x: z.number().int(),
  y: z.number().int(),
  w: z.number().int(),
  h: z.number().int(),
});

export type FigureBbox = z.infer<typeof FigureBboxSchema>;

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
  /** Equation OCR (UniMERNet) LaTeX for kind='equation' figures (ADR 0001). */
  extracted_latex: z.string().optional(),
  /**
   * YOLO crop region (PR-F3 ResultResponse sync) — null/absent for
   * whole-frame `keyframe` rows.
   */
  bbox: FigureBboxSchema.nullable().optional(),
  /**
   * 'unverified' iff extraction_conf < LOW_CONF_THRESHOLD (0.7) — flagged,
   * never silently embedded (ADR 0003 D3 / ADR 0004 G3). 'verified' is
   * human-set.
   */
  verification_status: z.enum(['pending', 'unverified', 'verified']).default('pending'),
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
