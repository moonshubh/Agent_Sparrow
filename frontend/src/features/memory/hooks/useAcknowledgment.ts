"use client";

import {
  useAcknowledgeEntity,
  useAcknowledgeRelationship,
} from "./useMemoryData";

export function useAcknowledgment() {
  const entity = useAcknowledgeEntity();
  const relationship = useAcknowledgeRelationship();

  return {
    entity,
    relationship,
  };
}
