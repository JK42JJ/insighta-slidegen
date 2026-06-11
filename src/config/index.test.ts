/**
 * Tests for the env funnel — focused on the CONTRACT_model-endpoints §5 keys:
 * safe defaults (unset = existing behavior) and the dev-mode refusal of live
 * model-endpoint tokens (mirrors the VISION_API_PROVIDER prod-only gating).
 */
import { beforeAll, describe, expect, it, vi } from 'vitest';

/** Minimal valid env — required keys only, no model-endpoint keys set. */
const BASE_ENV: NodeJS.ProcessEnv = {
  DATABASE_URL: 'postgresql://user:pass@localhost:5432/slidegen_test',
  DIRECT_URL: 'postgresql://user:pass@localhost:5432/slidegen_test',
  SUPABASE_URL: 'https://stub-project.supabase.test',
  SUPABASE_SERVICE_ROLE_KEY: 'stub-service-role-key',
  SUPABASE_ANON_KEY: 'stub-anon-key-value',
  GOOGLE_OAUTH_CLIENT_ID: 'stub-client-id',
  GOOGLE_OAUTH_CLIENT_SECRET: 'stub-client-secret',
  GOOGLE_OAUTH_REDIRECT_URI: 'http://localhost:3000/oauth/callback',
};

let parseEnv: typeof import('@/config').parseEnv;

beforeAll(async () => {
  // The module parses process.env at import time; satisfy required keys first.
  for (const [key, value] of Object.entries(BASE_ENV)) {
    vi.stubEnv(key, value ?? '');
  }
  ({ parseEnv } = await import('@/config'));
});

describe('model-endpoint keys (§5) — defaults', () => {
  it('unset keys = existing behavior: mock backend, no endpoints, 15-min presign', () => {
    const config = parseEnv({ ...BASE_ENV });
    expect(config.SLIDEGEN_VLM_BACKEND).toBe('mock');
    expect(config.SLIDEGEN_VLM_BASE_URL).toBeUndefined();
    expect(config.SLIDEGEN_VLM_TOKEN).toBeUndefined();
    expect(config.SLIDEGEN_VLM_MODEL).toBeUndefined();
    expect(config.SLIDEGEN_YOLO_BASE_URL).toBeUndefined();
    expect(config.SLIDEGEN_YOLO_TOKEN).toBeUndefined();
    expect(config.SLIDEGEN_S3_BUCKET).toBeUndefined();
    expect(config.SLIDEGEN_PRESIGN_EXPIRY_SEC).toBe(900);
  });

  it('treats empty-string values (blank .env lines) as unset', () => {
    const config = parseEnv({
      ...BASE_ENV,
      SLIDEGEN_VLM_BACKEND: '',
      SLIDEGEN_VLM_BASE_URL: '',
      SLIDEGEN_VLM_TOKEN: '',
      SLIDEGEN_YOLO_TOKEN: '',
      SLIDEGEN_PRESIGN_EXPIRY_SEC: '',
    });
    expect(config.SLIDEGEN_VLM_BACKEND).toBe('mock');
    expect(config.SLIDEGEN_VLM_BASE_URL).toBeUndefined();
    expect(config.SLIDEGEN_PRESIGN_EXPIRY_SEC).toBe(900);
  });

  it('coerces SLIDEGEN_PRESIGN_EXPIRY_SEC from string', () => {
    const config = parseEnv({ ...BASE_ENV, SLIDEGEN_PRESIGN_EXPIRY_SEC: '600' });
    expect(config.SLIDEGEN_PRESIGN_EXPIRY_SEC).toBe(600);
  });
});

describe('model-endpoint keys (§5) — dev-mode live-token refusal', () => {
  it('refuses SLIDEGEN_VLM_TOKEN in dev without http opt-in', () => {
    expect(() =>
      parseEnv({ ...BASE_ENV, SLIDEGEN_MODE: 'dev', SLIDEGEN_VLM_TOKEN: 'live-token' })
    ).toThrow(/prod\/opt-in only/);
  });

  it('refuses SLIDEGEN_YOLO_TOKEN when SLIDEGEN_MODE defaults to dev', () => {
    expect(() => parseEnv({ ...BASE_ENV, SLIDEGEN_YOLO_TOKEN: 'live-token' })).toThrow(
      /SLIDEGEN_YOLO_TOKEN/
    );
  });

  it('allows live tokens with explicit SLIDEGEN_VLM_BACKEND=http opt-in', () => {
    const config = parseEnv({
      ...BASE_ENV,
      SLIDEGEN_MODE: 'dev',
      SLIDEGEN_VLM_BACKEND: 'http',
      SLIDEGEN_VLM_TOKEN: 'opt-in-token',
      SLIDEGEN_YOLO_TOKEN: 'opt-in-token',
    });
    expect(config.SLIDEGEN_VLM_BACKEND).toBe('http');
    expect(config.SLIDEGEN_VLM_TOKEN).toBe('opt-in-token');
  });

  it('allows live tokens in prod mode without opt-in', () => {
    const config = parseEnv({
      ...BASE_ENV,
      SLIDEGEN_MODE: 'prod',
      SLIDEGEN_VLM_TOKEN: 'prod-token',
      SLIDEGEN_YOLO_TOKEN: 'prod-token',
    });
    expect(config.SLIDEGEN_VLM_TOKEN).toBe('prod-token');
  });

  it('non-http local backends (mlx) do NOT unlock live tokens in dev', () => {
    expect(() =>
      parseEnv({
        ...BASE_ENV,
        SLIDEGEN_MODE: 'dev',
        SLIDEGEN_VLM_BACKEND: 'mlx',
        SLIDEGEN_VLM_TOKEN: 'live-token',
      })
    ).toThrow(/prod\/opt-in only/);
  });
});

describe('OPENROUTER_API_KEY — prod-only refusal (LLM API ban, PR-F3)', () => {
  it('defaults to undefined and treats empty string as unset', () => {
    expect(parseEnv({ ...BASE_ENV }).OPENROUTER_API_KEY).toBeUndefined();
    expect(parseEnv({ ...BASE_ENV, OPENROUTER_API_KEY: '' }).OPENROUTER_API_KEY).toBeUndefined();
  });

  it('refuses the key when SLIDEGEN_MODE=dev (explicit or defaulted)', () => {
    expect(() =>
      parseEnv({ ...BASE_ENV, SLIDEGEN_MODE: 'dev', OPENROUTER_API_KEY: 'sk-or-stub' })
    ).toThrow(/prod-only \(LLM API ban\)/);
    expect(() => parseEnv({ ...BASE_ENV, OPENROUTER_API_KEY: 'sk-or-stub' })).toThrow(
      /OPENROUTER_API_KEY/
    );
  });

  it('has NO opt-in escape: SLIDEGEN_VLM_BACKEND=http does not unlock it in dev', () => {
    expect(() =>
      parseEnv({
        ...BASE_ENV,
        SLIDEGEN_MODE: 'dev',
        SLIDEGEN_VLM_BACKEND: 'http',
        OPENROUTER_API_KEY: 'sk-or-stub',
      })
    ).toThrow(/LLM API ban/);
  });

  it('allows the key in prod mode', () => {
    const config = parseEnv({
      ...BASE_ENV,
      SLIDEGEN_MODE: 'prod',
      OPENROUTER_API_KEY: 'sk-or-stub',
    });
    expect(config.OPENROUTER_API_KEY).toBe('sk-or-stub');
  });
});
