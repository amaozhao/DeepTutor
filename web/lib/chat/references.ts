type NotebookRecordLike = {
  id: string;
  notebookId: string;
  notebookName: string;
};

type HistorySessionLike = {
  sessionId: string;
};

export type NotebookReferencePayload = {
  notebook_id: string;
  record_ids: string[];
};

export type NotebookReferenceGroup = {
  notebookId: string;
  notebookName: string;
  count: number;
};

export function buildNotebookReferencesPayload(
  records: readonly NotebookRecordLike[],
): NotebookReferencePayload[] {
  const grouped = new Map<string, string[]>();
  records.forEach((record) => {
    const current = grouped.get(record.notebookId) || [];
    current.push(record.id);
    grouped.set(record.notebookId, current);
  });
  return Array.from(grouped.entries()).map(([notebook_id, record_ids]) => ({
    notebook_id,
    record_ids,
  }));
}

export function buildNotebookReferenceGroups(
  records: readonly NotebookRecordLike[],
): NotebookReferenceGroup[] {
  const groups = new Map<string, { notebookName: string; count: number }>();
  records.forEach((record) => {
    const existing = groups.get(record.notebookId);
    if (existing) {
      existing.count += 1;
    } else {
      groups.set(record.notebookId, {
        notebookName: record.notebookName,
        count: 1,
      });
    }
  });
  return Array.from(groups.entries()).map(([notebookId, value]) => ({
    notebookId,
    ...value,
  }));
}

export function historyReferenceIds(
  sessions: readonly HistorySessionLike[],
): string[] {
  return sessions.map((session) => session.sessionId);
}

export function uniqueHistoryReferenceIds(
  ...sessionGroups: readonly HistorySessionLike[][]
): string[] {
  return Array.from(new Set(sessionGroups.flatMap(historyReferenceIds)));
}
