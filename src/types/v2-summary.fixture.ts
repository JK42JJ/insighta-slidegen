/**
 * Synthetic v2 rich-summary fixture for unit tests.
 *
 * Shape mirrors the REAL layered v2 row (parent insighta repo,
 * `src/modules/skills/rich-summary-v2-prompt.ts` RichSummaryV2Layered):
 * `segments` is an object { sections, atoms }; `core` has no title/qa_pairs;
 * atoms live in segments, not analysis.
 *
 * PUBLIC repo rule: video ids in fixtures are SYNTHETIC (11 chars, not a
 * real YouTube id). Excluded from the build via tsconfig "**\/*.fixture.ts".
 */

/** Synthetic 11-character video id — NOT a real YouTube id. */
export const SYNTHETIC_VIDEO_ID = 'AAAAAAAAAA1';

/**
 * Builds a realistic v2 `video_rich_summaries` row (as returned by
 * prisma.video_rich_summaries.findUnique). Returned as a fresh deep clone
 * so tests can mutate freely; pass `overrides` to replace top-level columns.
 */
export function makeV2Row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const row: Record<string, unknown> = {
    video_id: SYNTHETIC_VIDEO_ID,
    template_version: 'v2',
    source_language: 'en',
    quality_flag: 'pass',
    transcript_used: true,
    core: {
      one_liner: 'Spaced repetition basics',
      domain: 'learning',
      depth_level: 'beginner',
      content_type: 'tutorial',
      target_audience: 'Learners who want to retain more from study sessions',
    },
    analysis: {
      core_argument:
        'Spaced repetition beats cramming because review timing matters more than review volume. Scheduling reviews just before forgetting maximizes retention per minute studied.',
      key_concepts: [
        { term: 'Spaced repetition', definition: 'Reviewing material at increasing intervals' },
        { term: 'Forgetting curve', definition: 'Exponential decay of memory without review' },
        {
          term: 'Active recall',
          definition: 'Retrieving answers from memory instead of rereading',
        },
      ],
      entities: [
        { name: 'Spaced repetition', type: 'concept' },
        { name: 'Hermann Ebbinghaus', type: 'person' },
        { name: 'Anki', type: 'tool' },
      ],
      actionables: [
        'Create a flashcard deck for the current study topic',
        'Schedule the first review 24 hours after learning',
        'Replace one rereading session per week with active recall',
      ],
      mandala_fit: {
        suggested_goals: ['Build a daily review habit', 'Improve long-term retention'],
        relevance_rationale: 'Directly teaches a retention technique for study goals',
        mandala_relevance_pct: 72,
      },
      bias_signals: {
        has_ad: false,
        is_sponsored: false,
        subjectivity_level: 'low',
        notes: '',
      },
      prerequisites: '',
    },
    lora: {
      qa_pairs: [
        {
          level: 1,
          q: 'Why is spaced repetition more effective than cramming?',
          a: 'Because reviews timed near the point of forgetting strengthen memory most.',
          context: 'video',
        },
      ],
    },
    segments: {
      sections: [
        {
          idx: 0,
          from_sec: 0,
          to_sec: 95,
          title: 'Why cramming fails',
          summary: 'Introduces the forgetting curve and why massed practice decays fast.',
          relevance_pct: 60,
          key_points: [
            { text: 'Memory decays exponentially without review', timestamp_sec: 40 },
            { text: 'Cramming optimizes for the test date only', timestamp_sec: 75 },
          ],
        },
        {
          idx: 1,
          from_sec: 95,
          to_sec: 240,
          title: 'The spacing effect',
          summary: 'Explains interval scheduling and the spacing effect evidence.',
          relevance_pct: 85,
          key_points: [{ text: 'Expanding intervals beat fixed intervals', timestamp_sec: 150 }],
        },
        {
          idx: 2,
          from_sec: 240,
          to_sec: 360,
          title: 'Setting up a review system',
          relevance_pct: 70,
        },
      ],
      atoms: [
        {
          idx: 0,
          type: 'fact',
          text: 'Most forgetting happens within 24 hours of learning',
          timestamp_sec: 35,
          entity_refs: ['Hermann Ebbinghaus'],
        },
        {
          idx: 1,
          type: 'argument',
          text: 'Review timing matters more than total review time',
          timestamp_sec: 180,
        },
        {
          idx: 2,
          type: 'tip',
          text: 'Start with 20 new cards per day to avoid review backlog',
          timestamp_sec: 300,
          entity_refs: ['Anki'],
        },
      ],
    },
    mandala_relevance_pct: 72,
  };
  return { ...structuredClone(row), ...overrides };
}
