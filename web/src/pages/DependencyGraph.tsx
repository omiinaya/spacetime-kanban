import { useMemo } from 'react'
import { X, Map as MapIcon } from 'lucide-react'
import type { Task } from '../hooks/useRealtimeTasks'

const NODE_W = 180
const NODE_H = 52
const LEVEL_GAP = 100
const NODE_GAP = 20
const PAD_X = 40
const PAD_Y = 40

const STATUS_COLORS: Record<string, string> = {
  available: '#3b82f6',
  in_progress: '#22c55e',
  blocked: '#ef4444',
  done: '#6b7280',
}

const PRIO_LABELS: Record<number, string> = { 0: 'U', 1: 'H', 2: 'M', 3: 'L' }

function layoutGraph(tasks: Task[]) {
  // Build adjacency
  const byId = new Map(tasks.map(t => [t.id, t]))
  const outgoing = new Map<string, string[]>()  // id → [dependent ids]
  const incoming = new Map<string, string[]>()  // id → [dependency ids]

  for (const t of tasks) {
    outgoing.set(t.id, [])
    incoming.set(t.id, [])
  }
  for (const t of tasks) {
    if (t.dependsOn && byId.has(t.dependsOn)) {
      const outList = outgoing.get(t.dependsOn)
      if (outList) outList.push(t.id)
      const inList = incoming.get(t.id)
      if (inList) inList.push(t.dependsOn)
    }
  }

  // Topological sort (Kahn's algorithm)
  const inDeg = new Map<string, number>()
  for (const t of tasks) inDeg.set(t.id, incoming.get(t.id)?.length ?? 0)

  const queue: string[] = []
  for (const [id, deg] of inDeg) if (deg === 0) queue.push(id)

  const sorted: string[] = []
  while (queue.length) {
    const id = queue.shift() as string
    sorted.push(id)
    for (const dep of outgoing.get(id) || []) {
      const d = (inDeg.get(dep) ?? 0) - 1
      inDeg.set(dep, d)
      if (d === 0) queue.push(dep)
    }
  }
  // Add any cycles at the end
  for (const [id, deg] of inDeg) if (deg > 0) sorted.push(id)

  // Assign layers
  const layer = new Map<string, number>()
  for (const id of sorted) {
    const deps = incoming.get(id) || []
    if (deps.length === 0) {
      layer.set(id, 0)
    } else {
      layer.set(id, Math.max(...deps.map(d => layer.get(d) ?? 0)) + 1)
    }
  }

  // Group by layer
  const layers = new Map<number, string[]>()
  for (const [id, l] of layer) {
    if (!layers.has(l)) layers.set(l, [])
    layers.get(l)?.push(id)
  }

  // Position nodes
  const positions = new Map<string, { x: number; y: number }>()
  for (const [lvl, ids] of layers) {
    const totalW = ids.length * NODE_W + (ids.length - 1) * NODE_GAP
    const startX = -totalW / 2 + NODE_W / 2
    ids.forEach((id, i) => {
      positions.set(id, { x: startX + i * (NODE_W + NODE_GAP), y: lvl * (NODE_H + LEVEL_GAP) })
    })
  }

  return { positions, outgoing, incoming, byId, sorted, layers }
}

function computeViewBox(positions: Map<string, { x: number; y: number }>) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const { x, y } of positions.values()) {
    minX = Math.min(minX, x - NODE_W / 2)
    minY = Math.min(minY, y - NODE_H / 2)
    maxX = Math.max(maxX, x + NODE_W / 2)
    maxY = Math.max(maxY, y + NODE_H / 2)
  }
  const w = maxX - minX + PAD_X * 2
  const h = maxY - minY + PAD_Y * 2
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  return { viewBox: `${cx - w / 2} ${cy - h / 2} ${w} ${h}`, center: { x: cx, y: cy }, dims: { w, h } }
}

export default function DependencyGraph({
  tasks, onSelectTask, onClose,
}: {
  tasks: Task[]
  onSelectTask: (id: string) => void
  onClose: () => void
}) {
  const graph = useMemo(() => layoutGraph(tasks), [tasks])
  const vb = useMemo(() => computeViewBox(graph?.positions ?? new Map()), [graph])
  if (!graph) return null
  const { positions, outgoing, byId } = graph

  const edges: { from: string; to: string; x1: number; y1: number; x2: number; y2: number; mx: number; my: number }[] = []
  for (const [id, deps] of outgoing) {
    const p1 = positions.get(id)
    if (!p1) continue
    for (const depId of deps) {
      const p2 = positions.get(depId)
      if (!p2) continue
      const x1 = p1.x + NODE_W / 2
      const y1 = p1.y + NODE_H / 2
      const x2 = p2.x - NODE_W / 2
      const y2 = p2.y + NODE_H / 2
      const mx = (x1 + x2) / 2
      const my = (y1 + y2) / 2 - 16
      edges.push({ from: id, to: depId, x1, y1, x2, y2, mx, my })
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70" onClick={onClose} role="dialog" aria-modal="true">
      <div className="flex items-center justify-between p-3 bg-[var(--color-card)] border-b border-[var(--color-border)]" onClick={e => e.stopPropagation()}>
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <MapIcon className="w-5 h-5 text-violet-400" /> Dependency Graph
          <span className="text-xs font-normal text-[var(--color-muted)]">({tasks.length} tasks)</span>
        </h2>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[var(--color-muted)] hidden sm:inline">Click a node to select · Dep arrows show flow</span>
          <button onClick={onClose} aria-label="Close dependency graph" className="p-1.5 rounded hover:bg-white/10 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden" onClick={e => e.stopPropagation()}>
        <svg
          viewBox={vb.viewBox}
          className="w-full h-full min-h-[400px]"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Edges */}
          {edges.map((e, i) => (
            <g key={`edge-${i}`}>
              <defs>
                <marker id={`arrow-${i}`} markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                  <path d="M0,0 L8,3 L0,6 Z" fill="var(--color-border)" />
                </marker>
              </defs>
              <path
                d={`M${e.x1},${e.y1} C${e.mx},${e.y1} ${e.mx},${e.y2} ${e.x2},${e.y2}`}
                fill="none"
                stroke="var(--color-border)"
                strokeWidth="1.5"
                markerEnd={`url(#arrow-${i})`}
              />
            </g>
          ))}

          {/* Nodes */}
          {[...positions.entries()].map(([id, pos]) => {
            const task = byId.get(id)
            if (!task) return null
            const sc = STATUS_COLORS[task.status] || '#6b7280'
            return (
              <g
                key={id}
                className="cursor-pointer"
                onClick={() => onSelectTask(id)}
              >
                <rect
                  x={pos.x - NODE_W / 2}
                  y={pos.y - NODE_H / 2}
                  width={NODE_W}
                  height={NODE_H}
                  rx="8"
                  ry="8"
                  fill="var(--color-card)"
                  stroke={sc}
                  strokeWidth="2"
                />
                <text
                  x={pos.x}
                  y={pos.y - 8}
                  textAnchor="middle"
                  fill="var(--color-foreground)"
                  fontSize="12"
                  fontWeight="500"
                >
                  {task.title.length > 24 ? task.title.slice(0, 23) + '…' : task.title}
                </text>
                <g>
                  <rect
                    x={pos.x - NODE_W / 2 + 8}
                    y={pos.y + 8}
                    width="36"
                    height="16"
                    rx="4"
                    fill={sc + '33'}
                  />
                  <text
                    x={pos.x - NODE_W / 2 + 26}
                    y={pos.y + 19}
                    textAnchor="middle"
                    fill={sc}
                    fontSize="9"
                    fontWeight="600"
                  >
                    {task.status === 'done' ? 'DONE' : task.status === 'in_progress' ? 'ACTIVE' : task.status === 'blocked' ? 'BLOCKED' : 'READY'}
                  </text>
                </g>
                {(task.requiredSkills || task.priority >= 0) && (
                  <text
                    x={pos.x + NODE_W / 2 - 8}
                    y={pos.y + 19}
                    textAnchor="end"
                    fill="var(--color-muted)"
                    fontSize="9"
                  >
                    {PRIO_LABELS[task.priority] || ''}{task.requiredSkills ? ` · ${task.requiredSkills.split(',').length}s` : ''}
                  </text>
                )}
              </g>
            )
          })}

          {/* Legend */}
          <g transform={`translate(${(() => {
            const parts = vb.viewBox.split(' ')
            return Number(parts[0] ?? 0) + 8
          })()}, ${(() => {
            const parts = vb.viewBox.split(' ')
            return Number(parts[1] ?? 0) + 8
          })()})`}>
            <rect x="0" y="0" width="170" height="90" rx="6" fill="var(--color-card)" opacity="0.9" stroke="var(--color-border)" strokeWidth="1" />
            <text x="8" y="16" fill="var(--color-foreground)" fontSize="10" fontWeight="600">Legend</text>
            {Object.entries(STATUS_COLORS).map(([status, color], i) => (
              <g key={status} transform={`translate(8, ${26 + i * 16})`}>
                <rect x="0" y="-5" width="10" height="10" rx="2" fill={color} />
                <text x="16" y="3" fill="var(--color-muted-foreground)" fontSize="9" textAnchor="start" textRendering="geometricPrecision">
                  {status.replace('_', ' ')}
                </text>
              </g>
            ))}
          </g>
        </svg>
      </div>
    </div>
  )
}
