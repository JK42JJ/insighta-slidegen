/**
 * Resolves a user's card (UserVideoState) to its underlying YouTube video id
 * and associated metadata needed by the slidegen pipeline.
 *
 * Join path (READ-ONLY against insighta Supabase):
 *   user_video_states.video_id (UUID FK)
 *     → youtube_videos.id (UUID PK)
 *     → youtube_videos.youtube_video_id (VARCHAR 11)
 *
 * The Prisma read-mirror models (youtube_videos, video_rich_summaries) are
 * declared in prisma/schema.prisma under the "READ MIRROR" section; this
 * function never writes to insighta tables.
 */
import { PrismaClient } from "@prisma/client";

export interface CardVideoResult {
  youtubeVideoId: string;
  title: string | null;
  channelTitle: string | null;
  durationSeconds: number | null;
}

/**
 * Resolves a card id to the YouTube video it represents.
 *
 * Algorithm:
 *   1. Look up youtube_videos row where id = cardVideoId obtained from
 *      the insighta user_video_states table (joined server-side or via
 *      known video_id UUID).
 *   2. Return youtube_video_id (11-char) + display metadata.
 *
 * @param cardId - The user_video_states.id UUID string.
 * @param userId - Optional: assert ownership before resolving.
 * @returns CardVideoResult with youtubeVideoId guaranteed non-null.
 * @throws Error if card not found, ownership mismatch, or no youtube_video_id.
 *
 * TODO: implement — join user_video_states (read-mirror not yet in schema;
 *   add if needed) → youtube_videos via video_id UUID foreign key.
 *   Until read-mirror for user_video_states is added, accept videoUUID
 *   directly and look up youtube_videos.id = videoUUID.
 */
export async function resolveCardToVideo(
  _cardId: string,
  _userId?: string,
  _prisma?: PrismaClient
): Promise<CardVideoResult> {
  // TODO: join user_video_states → youtube_videos on video_id UUID FK,
  // assert ownership when _userId is provided, return CardVideoResult.
  throw new Error(
    "TODO: resolveCardToVideo — join user_video_states → youtube_videos, return youtubeVideoId"
  );
}
