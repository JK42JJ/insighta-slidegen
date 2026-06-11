/**
 * Presign tests (PR-H1). getSignedUrl computes SigV4 signatures OFFLINE —
 * no network, no real AWS account; stub credentials via env.
 */
import { beforeAll, describe, expect, it } from 'vitest';
import { S3Client } from '@aws-sdk/client-s3';
import { PresignConfigError, presignGetUrl, presignPutUrl, type PresignConfig } from '@/s3/presign';

const STUB_EXPIRY_SEC = 900;

const CONFIG: PresignConfig = {
  SLIDEGEN_S3_BUCKET: 'stub-bucket',
  SLIDEGEN_S3_REGION: 'us-west-2',
  SLIDEGEN_PRESIGN_EXPIRY_SEC: STUB_EXPIRY_SEC,
};

let client: S3Client;

beforeAll(() => {
  client = new S3Client({
    region: CONFIG.SLIDEGEN_S3_REGION,
    credentials: { accessKeyId: 'stub-access-key', secretAccessKey: 'stub-secret-key' },
  });
});

describe('presignGetUrl', () => {
  it('issues a signed GET URL bound to bucket + key with the configured expiry', async () => {
    const url = await presignGetUrl(CONFIG, 'frames/synthvid001/0001.jpg', client);
    const parsed = new URL(url);
    expect(parsed.hostname).toContain('stub-bucket');
    expect(parsed.pathname).toBe('/frames/synthvid001/0001.jpg');
    expect(parsed.searchParams.get('X-Amz-Expires')).toBe(String(STUB_EXPIRY_SEC));
    expect(parsed.searchParams.get('X-Amz-Signature')).toBeTruthy();
    // The signature never embeds the secret.
    expect(url).not.toContain('stub-secret-key');
  });

  it('refuses to issue without a bucket (fail-closed)', async () => {
    await expect(
      presignGetUrl({ SLIDEGEN_PRESIGN_EXPIRY_SEC: STUB_EXPIRY_SEC }, 'k', client)
    ).rejects.toThrow(PresignConfigError);
  });
});

describe('presignPutUrl', () => {
  it('issues a PUT URL distinct from the GET signature for the same key', async () => {
    const key = 'artifacts/synthvid001/deck.pptx';
    const getUrl = await presignGetUrl(CONFIG, key, client);
    const putUrl = await presignPutUrl(CONFIG, key, client);
    expect(new URL(putUrl).pathname).toBe(`/${key}`);
    // Same key, different HTTP method → different SigV4 signature.
    expect(new URL(putUrl).searchParams.get('X-Amz-Signature')).not.toBe(
      new URL(getUrl).searchParams.get('X-Amz-Signature')
    );
  });

  it('binds ContentType into the signature when provided', async () => {
    const url = await presignPutUrl(CONFIG, 'frames/x.jpg', client, 'image/jpeg');
    expect(new URL(url).searchParams.get('X-Amz-SignedHeaders')).toContain('content-type');
  });
});
