export interface Field {
  id: string
  label: string
  type: string
  required: boolean
  requiredWhen?: [string, string]
  extensions?: string[]
  default?: string | number
  hint?: string
  choices?: string[]
  min?: number
  max?: number
  integer?: boolean
}
export interface Stage { id: string; title: string; action: string; help: string; fields: Field[]; outputs: string[]; skill: string; review?: boolean }
export interface Artifact { role: string; path: string; remote: boolean }
export interface WorkflowState {
  version: number
  id: string
  sessionId: string
  revision: number
  current: number
  status: string
  parameters: Record<string, Record<string, unknown>>
  stages: { id: string; status: string; artifacts: Artifact[] }[]
  traces: { time: string; text: string; kind: string }[]
  jobDirectory?: string
  executionId?: string
  additionalRequest?: string
}
export const STAGES: Stage[]
export function missingSoftware(stage: Stage, software: unknown): { field: string; message: string } | null
export class WorkflowStore {
  constructor(directory: string)
  load(sessionId: string): WorkflowState | null
  create(sessionId: string): WorkflowState
  submit(sessionId: string, revision: number, raw: unknown, software: unknown): WorkflowState
  confirm(sessionId: string, revision: number): WorkflowState
  adjust(sessionId: string, revision: number, feedback: unknown): WorkflowState
  hasRunning(): boolean
}
