import { extname } from 'node:path'
import { readFileSync, statSync } from 'node:fs'
import type { Stage, WorkflowStore } from '../../cae-workflow/state.cjs'

export function workflowArtifact(store: WorkflowStore, sessionId: string, file: unknown): string {
  const state = store.load(sessionId)
  if (typeof file !== 'string' || !state?.stages.some(stage => stage.artifacts.some(artifact => artifact.path === file && !artifact.remote))) throw new Error('只能打开当前对话已经验证的本机产物。')
  return file
}

export function workflowPreview(store: WorkflowStore, sessionId: string, file: unknown): string {
  const path = workflowArtifact(store, sessionId, file)
  const extension = extname(path).slice(1).toLowerCase()
  const mime: Record<string, string> = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp' }
  if (!mime[extension] || statSync(path).size > 20 * 1024 * 1024) throw new Error('预览仅支持不超过 20 MB 的 PNG、JPEG、GIF 或 WebP 图片，请打开文件查看。')
  return `data:${mime[extension]};base64,${readFileSync(path).toString('base64')}`
}

export function workflowField(store: WorkflowStore, sessionId: string, fieldId: unknown, stages: Stage[]) {
  const state = store.load(sessionId)
  const field = state && stages[state.current].fields.find(field => field.id === fieldId && ['file', 'directory'].includes(field.type))
  if (!field || state.status === 'running') throw new Error('当前参数不支持选择路径。')
  return field
}
