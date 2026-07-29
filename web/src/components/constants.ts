import { type TaskStatus } from '../hooks/useRealtimeTasks'

export const PRIORITY_LABELS: Record<number, string> = {
  0: 'Urgent',
  1: 'High',
  2: 'Medium',
  3: 'Low',
}

export const PRIORITY_COLORS: Record<number, string> = {
  0: 'bg-red-500/20 text-red-400',
  1: 'bg-orange-500/20 text-orange-400',
  2: 'bg-blue-500/20 text-blue-400',
  3: 'bg-slate-500/20 text-slate-400',
}

export const PRIORITY_COLORS_VIBRANT: Record<number, string> = {
  0: 'bg-red-600/25 text-red-300',
  1: 'bg-orange-500/25 text-orange-300',
  2: 'bg-blue-500/25 text-blue-300',
  3: 'bg-slate-500/25 text-slate-300',
}

export const STATUS_COLORS: Record<string, string> = {
  available: 'bg-slate-500/20 text-slate-400',
  in_progress: 'bg-blue-500/20 text-blue-400',
  blocked: 'bg-red-500/20 text-red-400',
  done: 'bg-emerald-500/20 text-emerald-400',
}

export const STATUS_COLUMNS: TaskStatus[] = ['available', 'in_progress', 'blocked', 'done']

export const STATUS_LABELS: Record<string, string> = {
  available: 'Available',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  done: 'Done',
}

export interface TaskTemplate {
  name: string
  title: string
  description: string
  priority: number
  repo: string
  roadmap: string
  skills: string
  icon: string
}

export const BUILT_IN_TEMPLATES: TaskTemplate[] = [
  { name: 'Bug Fix', title: 'Fix: ', description: [
    '## Steps to Reproduce',
    '1. ',
    '2. ',
    '',
    '## Expected Behavior',
  ].join('\n'), priority: 1, repo: '', roadmap: '', skills: 'bug,fix', icon: 'Bug' },
  { name: 'Feature', title: 'Feat: ', description: [
    '## Summary',
    '',
    '## Acceptance Criteria',
    '- [ ] ',
  ].join('\n'), priority: 2, repo: '', roadmap: '', skills: 'fix,feat', icon: 'Lightbulb' },
  { name: 'Refactor', title: 'Refactor: ', description: [
    '## Context',
    '',
    '## Proposed Changes',
    '',
    '## Impact',
  ].join('\n'), priority: 2, repo: '', roadmap: '', skills: 'fix,refactor', icon: 'RefreshCw' },
  { name: 'Documentation', title: 'Docs: ', description: [
    '## What needs documenting?',
    '',
    '## Suggested Structure',
    '',
  ].join('\n'), priority: 3, repo: '', roadmap: '', skills: 'fix,docs', icon: 'BookOpen' },
  { name: 'Performance', title: 'Perf: ', description: [
    '## Current Behavior',
    '',
    '## Expected Improvement',
    '',
    '## Benchmarks',
  ].join('\n'), priority: 2, repo: '', roadmap: '', skills: 'fix,perf', icon: 'Zap' },
  { name: 'Test', title: 'Test: ', description: [
    '## What to test',
    '',
    '## Testing Strategy',
    '',
  ].join('\n'), priority: 2, repo: '', roadmap: '', skills: 'fix,test', icon: 'TestTube' },
  { name: 'Security', title: 'Security: ', description: [
    '## Vulnerability Description',
    '',
    '## Impact',
    '',
    '## Mitigation',
  ].join('\n'), priority: 1, repo: '', roadmap: '', skills: 'fix,security', icon: 'Shield' },
]
