/**
 * Central config module. All process.env reads are funnelled here.
 * No other file may read process.env directly (project convention).
 */
import { z } from 'zod';

const envSchema = z.object({
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
});

/** Parsed and validated env config. Throws at startup if required vars are missing. */
export const config = envSchema.parse(process.env);

export type Config = z.infer<typeof envSchema>;
