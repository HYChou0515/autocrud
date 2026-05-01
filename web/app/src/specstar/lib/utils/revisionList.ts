import type { RevisionInfo } from '../../types/api';
import type { Revision } from '../types/revision';

export function getRevisionId(revision: Revision): string | undefined {
  return revision.revision_id ?? revision.uid;
}

export function hasRevisionId(revisions: Revision[], revisionId: string): boolean {
  return revisions.some((revision) => getRevisionId(revision) === revisionId);
}

export function mergeRevisionsUnique(base: Revision[], extra: Revision[]): Revision[] {
  const seen = new Set(base.map((revision) => getRevisionId(revision)));
  const merged = [...base];
  for (const revision of extra) {
    const id = getRevisionId(revision);
    if (!id || seen.has(id)) {
      continue;
    }
    seen.add(id);
    merged.push(revision);
  }
  return merged;
}

export function ensureRevisionInList(revisions: Revision[], revision?: Revision): Revision[] {
  if (!revision) {
    return revisions;
  }
  const revisionId = getRevisionId(revision);
  if (!revisionId) {
    return revisions;
  }
  if (hasRevisionId(revisions, revisionId)) {
    return revisions;
  }
  return [...revisions, revision];
}

export function toRevisionFromInfo(info: RevisionInfo): Revision {
  return {
    revision_id: info.revision_id,
    uid: info.uid,
    status: info.status,
    created_time: info.created_time,
    updated_time: info.updated_time,
    created_by: info.created_by,
    updated_by: info.updated_by,
    parent_revision_id: info.parent_revision_id,
  };
}
