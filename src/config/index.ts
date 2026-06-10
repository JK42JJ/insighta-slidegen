/**
 * Central config module. All process.env reads are funnelled here.
 * No other file may read process.env directly (project convention).
 */
import { z } from 'zod';

/**
 * Presigned-URL expiry default: 15 min (CONTRACT_model-endpoints §4 —
 * tuning knob, not a secret). Long jobs re-request fresh URLs instead of
 * extending expiry.
 */
const DEFAULT_PRESIGN_EXPIRY_SEC = 900;

/**
 * Treats an empty-string env value as unset, so keys copied from .env.example
 * with blank values keep the "unset = existing behavior / no-op" guarantee.
 */
const emptyAsUndefined = <T extends z.ZodTypeAny>(
  schema: T
): z.ZodEffects<T, T['_output'], unknown> =>
  z.preprocess((value) => (value === '' ? undefined : value), schema);

const envObjectSchema = z.object({
  // Supabase / Postgres
  DATABASE_URL: z.string().url(),
  DIRECT_URL: z.string().url(),
  SUPABASE_URL: z.string().url(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(10),
  SUPABASE_ANON_KEY: z.string().min(10),

  // CV microservice (Mac Mini)
  SLIDEGEN_CV_SERVICE_URL: z.string().url().default('http://localhost:8077'),
  SLIDEGEN_CV_SERVICE_TOKEN: z.string().default(''),

  // Controls whether vision-API fallback is enabled.
  // "dev"  → local CV only, vision API hard-disabled.
  // "prod" → local CV preferred, API fallback allowed.
  SLIDEGEN_MODE: z.enum(['dev', 'prod']).default('dev'),

  // Google OAuth / Slides / Drive
  GOOGLE_OAUTH_CLIENT_ID: z.string(),
  GOOGLE_OAUTH_CLIENT_SECRET: z.string(),
  GOOGLE_OAUTH_REDIRECT_URI: z.string().url(),

  // Supabase Storage
  SUPABASE_STORAGE_BUCKET: z.string().default('slidegen-assets'),

  // Vision API provider used in prod fallback ("gemini" | "none").
  VISION_API_PROVIDER: z.enum(['gemini', 'none']).default('none'),
  GEMINI_API_KEY: z.string().optional(),

  // ── Model endpoints (docs/CONTRACT_model-endpoints.md v1.0 §5) ────────────
  // All optional/defaulted: unset = existing behavior (mock backend, no live
  // endpoints — CI-safe). "http" is the explicit opt-in to the live contract
  // endpoints (Qwen3-VL vLLM + DocLayout-YOLO); the dev-mode refusal below
  // mirrors the VISION_API_PROVIDER prod-only gating (ADR 0003 D2).
  SLIDEGEN_VLM_BACKEND: emptyAsUndefined(
    z.enum(['mock', 'transformers', 'mlx', 'http']).default('mock')
  ),
  SLIDEGEN_VLM_BASE_URL: emptyAsUndefined(z.string().url().optional()),
  SLIDEGEN_VLM_TOKEN: emptyAsUndefined(z.string().optional()),
  SLIDEGEN_VLM_MODEL: emptyAsUndefined(z.string().optional()),
  SLIDEGEN_YOLO_BASE_URL: emptyAsUndefined(z.string().url().optional()),
  SLIDEGEN_YOLO_TOKEN: emptyAsUndefined(z.string().optional()),
  // S3 handoff (§4) — the backend is the ONLY presign issuer; model hosts
  // receive presigned URLs, never credentials or the bucket name.
  SLIDEGEN_S3_BUCKET: emptyAsUndefined(z.string().optional()),
  SLIDEGEN_PRESIGN_EXPIRY_SEC: emptyAsUndefined(
    z.coerce.number().int().positive().default(DEFAULT_PRESIGN_EXPIRY_SEC)
  ),
});

const envSchema = envObjectSchema.superRefine((env, ctx) => {
  // §5 gating: live model-endpoint tokens are REFUSED in dev mode unless the
  // http backend was explicitly opted into. Dev/test/CI must never be able to
  // reach the live endpoints by accident (mirror of VISION_API_PROVIDER rule).
  if (env.SLIDEGEN_MODE === 'dev' && env.SLIDEGEN_VLM_BACKEND !== 'http') {
    for (const key of ['SLIDEGEN_VLM_TOKEN', 'SLIDEGEN_YOLO_TOKEN'] as const) {
      if (env[key]) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [key],
          message:
            `${key} is set but SLIDEGEN_MODE=dev without SLIDEGEN_VLM_BACKEND=http ` +
            'opt-in — live model endpoints are prod/opt-in only (CONTRACT_model-endpoints §5).',
        });
      }
    }
  }
});

export type Config = z.infer<typeof envSchema>;

/**
 * Parses and validates an env mapping. Exported so tests can exercise the §5
 * dev-mode refusal without mutating process.env; runtime code uses `config`.
 */
export function parseEnv(env: NodeJS.ProcessEnv): Config {
  return envSchema.parse(env);
}

/** Parsed and validated env config. Throws at startup if required vars are missing. */
export const config = parseEnv(process.env);
