/**
 * Status normalization helpers.
 *
 * SpacetimeDB unit enums deserialize on the client as `{ tag: "InProgress" }`
 * objects. The rest of the app was written against lowercase snake strings
 * (`'available'`, `'in_progress'`, `'blocked'`, `'done'`), so we normalize at
 * the data boundary (useRealtimeTasks) to keep components simple.
 */

/** PascalCase tag → lowercase snake: "InProgress" → "in_progress" */
export function tagToSnake(tag: string): string {
  return tag.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
}

/** STDB enum object { tag: "Available" } (or a plain string) → "available" */
export function statusToStr(status: unknown): string {
  if (typeof status === 'string') return tagToSnake(status);
  if (status && typeof status === 'object' && 'tag' in status) {
    return tagToSnake(String((status as { tag: unknown }).tag));
  }
  return String(status ?? '');
}

export type StdbStatusTag = 'Available' | 'InProgress' | 'Blocked' | 'Done';
export type StatusStr = 'available' | 'in_progress' | 'blocked' | 'done';
