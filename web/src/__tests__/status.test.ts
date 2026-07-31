import { describe, expect, it } from 'vitest';
import { statusToStr, tagToSnake } from '../lib/status';

describe('tagToSnake', () => {
  it('converts PascalCase to snake_case', () => {
    expect(tagToSnake('Available')).toBe('available');
    expect(tagToSnake('InProgress')).toBe('in_progress');
    expect(tagToSnake('Blocked')).toBe('blocked');
    expect(tagToSnake('Done')).toBe('done');
  });

  it('handles already-lowercase input', () => {
    expect(tagToSnake('available')).toBe('available');
    expect(tagToSnake('blocked')).toBe('blocked');
  });

  it('handles camelCase input (old server REST payloads)', () => {
    expect(tagToSnake('inProgress')).toBe('in_progress');
  });
});

describe('statusToStr', () => {
  it('converts STDB enum objects to lowercase snake strings', () => {
    expect(statusToStr({ tag: 'Available' })).toBe('available');
    expect(statusToStr({ tag: 'InProgress' })).toBe('in_progress');
    expect(statusToStr({ tag: 'Blocked' })).toBe('blocked');
    expect(statusToStr({ tag: 'Done' })).toBe('done');
  });

  it('normalizes plain string payloads (REST fallback path)', () => {
    expect(statusToStr('available')).toBe('available');
    expect(statusToStr('inProgress')).toBe('in_progress');
    expect(statusToStr('Blocked')).toBe('blocked');
  });

  it('falls back to String() for unknown shapes', () => {
    expect(statusToStr(undefined)).toBe('');
    expect(statusToStr(null)).toBe('');
    expect(statusToStr(2)).toBe('2');
  });
});
