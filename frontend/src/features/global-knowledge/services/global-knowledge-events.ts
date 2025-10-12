import type { GlobalKnowledgeTimelineEvent } from '@/features/global-knowledge/services/global-knowledge-api'

export const sortEventsDescending = (
  events: GlobalKnowledgeTimelineEvent[],
): GlobalKnowledgeTimelineEvent[] =>
  [...events].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )

export const upsertTimelineEvent = (
  existing: GlobalKnowledgeTimelineEvent[],
  incoming: GlobalKnowledgeTimelineEvent,
  maxSize = 150,
): GlobalKnowledgeTimelineEvent[] => {
  const filtered = existing.filter(event => event.event_id !== incoming.event_id)
  const next = [incoming, ...filtered]
  return sortEventsDescending(next).slice(0, maxSize)
}
