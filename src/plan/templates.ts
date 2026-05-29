/**
 * Layout enum and field-map definitions for slide templates.
 * All layout identifiers referenced here must match LayoutEnum in slide-manifest.ts.
 *
 * A LayoutFieldMap describes which v2 fields populate which template zones.
 * The planner (slide-planner.ts) reads these maps to build body_json for each slide.
 */
import { type Layout } from "@/types/slide-manifest";

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
  figureAspect?: "16:9" | "4:3" | "1:1";
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
 * TODO: fill in primarySource and zone wiring for each layout.
 * Current stubs document intent; real values come from UX spec.
 */
export const LAYOUT_MAP: Record<Layout, LayoutFieldMap> = {
  cover: {
    layout: "cover",
    primarySource: "core.title",
    zones: { title: "core.title", body: "core.one_liner" },
  },
  section_intro: {
    layout: "section_intro",
    primarySource: "segments[n].title",
    zones: { title: "segments[n].title", body: "segments[n].summary" },
  },
  key_points: {
    layout: "key_points",
    primarySource: "segments[n].key_points",
    zones: { title: "segments[n].title", body: "segments[n].key_points" },
    maxItems: 5,
  },
  qa_pair: {
    layout: "qa_pair",
    primarySource: "core.qa_pairs[n]",
    zones: { title: "core.qa_pairs[n].q", body: "core.qa_pairs[n].a" },
  },
  figure_full: {
    layout: "figure_full",
    primarySource: "cv_figure",
    zones: { title: "figure.caption", figureAspect: "16:9" },
  },
  figure_caption: {
    layout: "figure_caption",
    primarySource: "cv_figure",
    zones: {
      title: "figure.caption",
      body: "figure.caption",
      figureAspect: "4:3",
    },
  },
  timeline: {
    layout: "timeline",
    primarySource: "segments",
    zones: { title: "core.title", body: "segments[*].title" },
  },
  summary: {
    layout: "summary",
    primarySource: "core.key_concepts",
    zones: { title: "core.one_liner", body: "core.key_concepts" },
    maxItems: 6,
  },
  blank: {
    layout: "blank",
    primarySource: "",
    zones: {},
  },
};
