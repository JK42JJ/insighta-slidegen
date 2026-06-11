/**
 * S3 presigned-URL issuance (CONTRACT_model-endpoints §4, PR-H1).
 *
 * The backend is the ONLY presign issuer: model hosts (RunPod Qwen/YOLO) and
 * the Mac Mini CV service receive short-lived presigned URLs, never AWS
 * credentials and never the bucket name. AWS credentials come from the
 * default provider chain (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env in
 * prod — GH Secrets); this module never reads or logs them.
 */
import { GetObjectCommand, PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

export interface PresignConfig {
  SLIDEGEN_S3_BUCKET?: string;
  SLIDEGEN_S3_REGION?: string;
  /** Short-lived on purpose (§4): default 900 s, set via config. */
  SLIDEGEN_PRESIGN_EXPIRY_SEC: number;
}

export class PresignConfigError extends Error {}

function requireBucket(config: PresignConfig): string {
  if (!config.SLIDEGEN_S3_BUCKET) {
    throw new PresignConfigError(
      'SLIDEGEN_S3_BUCKET is not set — presigned URLs cannot be issued (§4)'
    );
  }
  return config.SLIDEGEN_S3_BUCKET;
}

/** One client per config; callers may pass their own (tests, pooling). */
export function buildS3Client(config: PresignConfig): S3Client {
  return new S3Client({
    ...(config.SLIDEGEN_S3_REGION ? { region: config.SLIDEGEN_S3_REGION } : {}),
  });
}

/** Presigned GET — what model hosts receive to fetch a frame/crop (§4). */
export async function presignGetUrl(
  config: PresignConfig,
  key: string,
  client?: S3Client
): Promise<string> {
  const bucket = requireBucket(config);
  const s3 = client ?? buildS3Client(config);
  return getSignedUrl(s3, new GetObjectCommand({ Bucket: bucket, Key: key }), {
    expiresIn: config.SLIDEGEN_PRESIGN_EXPIRY_SEC,
  });
}

/** Presigned PUT — what the CV service receives to upload frames/artifacts. */
export async function presignPutUrl(
  config: PresignConfig,
  key: string,
  client?: S3Client,
  contentType?: string
): Promise<string> {
  const bucket = requireBucket(config);
  const s3 = client ?? buildS3Client(config);
  return getSignedUrl(
    s3,
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      ...(contentType ? { ContentType: contentType } : {}),
    }),
    {
      expiresIn: config.SLIDEGEN_PRESIGN_EXPIRY_SEC,
      // The SDK hoists ContentType OUT of the signature by default (verified:
      // identical signatures with/without it). Force it into SignedHeaders so
      // the uploader is bound to the declared type.
      ...(contentType ? { signableHeaders: new Set(['content-type']) } : {}),
    }
  );
}
