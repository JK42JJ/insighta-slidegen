/**
 * Contract-shape tests for the TS zod mirrors (CONTRACT_model-endpoints v1.0).
 * Fixtures mirror the §3.3 example and the §2.2 output table verbatim.
 */
import { describe, expect, it } from 'vitest';
import {
  VlmCropClassificationSchema,
  VlmEquationOcrSchema,
  VlmRoutingDecisionSchema,
  YOLO_DEFAULT_CONF_THRESHOLD,
  YOLO_DEFAULT_MAX_BOXES,
  YoloDetectRequestSchema,
  YoloDetectResponseSchema,
  YoloErrorSchema,
  YoloHealthSchema,
} from '@/types/model-endpoints';

describe('VLM output schemas (§2.2)', () => {
  it('parses a mode A routing decision', () => {
    const parsed = VlmRoutingDecisionSchema.parse({
      is_slide: true,
      contains_graph: true,
      contains_equation: false,
      frame_type: 'chart',
      summary_hint: 'revenue trend',
      confidence: 0.9,
    });
    expect(parsed.frame_type).toBe('chart');
  });

  it('drops Qwen-emitted coordinates (§2.2: any bbox is ignored)', () => {
    const parsed = VlmRoutingDecisionSchema.parse({
      is_slide: true,
      contains_graph: false,
      contains_equation: false,
      frame_type: 'diagram',
      confidence: 0.8,
      bbox: [10, 20, 30, 40],
    });
    expect(parsed).not.toHaveProperty('bbox');
  });

  it('parses a mode B crop classification with struct defaulting', () => {
    const parsed = VlmCropClassificationSchema.parse({ kind: 'table', confidence: 0.7 });
    expect(parsed.struct).toEqual({});
  });

  it('parses a mode C equation OCR result', () => {
    const parsed = VlmEquationOcrSchema.parse({ latex: 'E = mc^2', confidence: 0.95 });
    expect(parsed.latex).toBe('E = mc^2');
  });

  it('rejects out-of-range confidence', () => {
    expect(() => VlmEquationOcrSchema.parse({ latex: 'x', confidence: 1.5 })).toThrow();
  });
});

describe('YOLO schemas (§3)', () => {
  it('applies §3.2 over-detect request defaults', () => {
    const parsed = YoloDetectRequestSchema.parse({
      image_url: 'https://example.invalid/frames/job-0001/f1.jpg?sig=stub',
    });
    expect(parsed.conf_threshold).toBe(YOLO_DEFAULT_CONF_THRESHOLD);
    expect(parsed.max_boxes).toBe(YOLO_DEFAULT_MAX_BOXES);
    expect(YOLO_DEFAULT_CONF_THRESHOLD).toBe(0.15);
    expect(YOLO_DEFAULT_MAX_BOXES).toBe(50);
  });

  it('parses the §3.3 response example (pixel bbox + advisory class)', () => {
    const parsed = YoloDetectResponseSchema.parse({
      image: { w: 1920, h: 1080 },
      model_version: 'doclayout-yolo-stub-0001',
      boxes: [
        { bbox: { x: 0, y: 0, w: 640, h: 360 }, class: 'table', score: 0.42 },
        // advisory-only: any class string must parse — never an enum gate
        { bbox: { x: 10, y: 20, w: 30, h: 40 }, class: 'isolate_formula', score: 0.2 },
      ],
    });
    expect(parsed.boxes).toHaveLength(2);
    expect(parsed.boxes[1].class).toBe('isolate_formula');
  });

  it('parses health and §3.4 error shapes', () => {
    expect(YoloHealthSchema.parse({ status: 'ok', model_version: 'v1' }).status).toBe('ok');
    const err = YoloErrorSchema.parse({
      status: 422,
      code: 'missing_image_url',
      message: 'image_url is required',
    });
    expect(err.code).toBe('missing_image_url');
  });

  it('rejects a box without bbox geometry', () => {
    expect(() =>
      YoloDetectResponseSchema.parse({
        image: { w: 1, h: 1 },
        model_version: 'v1',
        boxes: [{ class: 'table', score: 0.5 }],
      })
    ).toThrow();
  });
});
