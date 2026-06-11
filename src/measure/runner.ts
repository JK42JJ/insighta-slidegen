/**
 * ADR 0004 measurement runner (PR-H1).
 *
 * Iterates the sample set SEQUENTIALLY (real runs are GPU/LLM-heavy) through
 * an INJECTED pipeline function and collects per-video measurements. The real
 * prod pipeline wiring lands in PR-H2; tests inject stubs (LLM/vision API ban
 * — no live model call ever happens from this module or its tests).
 *
 * Sample-set policy (PUBLIC repo): real video IDs are tracked OUTSIDE the
 * repo (non-committed file, see loadSampleSet). Reports and logs reference
 * the anonymous `index` (V01…) ONLY — never the videoId.
 */
import fs from 'node:fs';
import { z } from 'zod';
import { JobStageSchema, type JobStage } from '@/types/job-stages';

/** One sample-set entry. videoId never appears in reports or logs. */
export const SampleEntrySchema = z.object({
  /** Anonymous index used in all reports/logs (e.g. "V01"). */
  index: z.string().min(1),
  /** Real YouTube video id — EXTERNAL tracking only, never committed/logged. */
  videoId: z.string().min(1),
});
export type SampleEntry = z.infer<typeof SampleEntrySchema>;

const SampleSetSchema = z.array(SampleEntrySchema).min(1);

/** Per-video measurement record (the per-video JSON of the PR-H design). */
export interface VideoMeasurement {
  index: string;
  /** G1 input: did validate_deck PASS within the attempt budget? */
  validatePass: boolean;
  /** G2 input: llm attempts consumed by the validate self-correction loop. */
  attempts: number;
  /** G3 input: extraction-confidence distribution (figures: formulas+charts). */
  conf: { belowThreshold: number; total: number };
  /** ADR 0004 attribution: stage a failed run died in (null = no failure). */
  failureStage: JobStage | null;
  error?: string;
}

export type PipelineFn = (entry: SampleEntry) => Promise<Omit<VideoMeasurement, 'index'>>;

/** Thrown by pipeline implementations to attribute a failure to a stage. */
export class StageFailureError extends Error {
  constructor(
    public readonly stage: JobStage,
    message: string
  ) {
    super(message);
    this.name = 'StageFailureError';
  }
}

/**
 * Loads the EXTERNAL (non-committed) sample-set file: a JSON array of
 * {index, videoId}. Throws when entries are malformed or indexes collide.
 */
export function loadSampleSet(filePath: string): SampleEntry[] {
  const parsed: unknown = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  const samples = SampleSetSchema.parse(parsed);
  const indexes = new Set(samples.map((s) => s.index));
  if (indexes.size !== samples.length) {
    throw new Error('sample set has duplicate index values');
  }
  return samples;
}

/**
 * Runs every sample through the injected pipeline. A pipeline failure never
 * aborts the run: it is recorded as a failed measurement, attributed via
 * StageFailureError.stage when available (otherwise failureStage stays null
 * and the error text is preserved for manual attribution).
 */
export async function runMeasurement(
  samples: SampleEntry[],
  pipeline: PipelineFn
): Promise<VideoMeasurement[]> {
  const results: VideoMeasurement[] = [];
  for (const entry of samples) {
    try {
      results.push({ index: entry.index, ...(await pipeline(entry)) });
    } catch (err) {
      const stage =
        err instanceof StageFailureError
          ? err.stage
          : (JobStageSchema.safeParse((err as { stage?: unknown })?.stage).data ?? null);
      results.push({
        index: entry.index,
        validatePass: false,
        attempts: 0,
        conf: { belowThreshold: 0, total: 0 },
        failureStage: stage,
        // Index only — never echo the videoId into reports/logs.
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }
  return results;
}
