// Read-only inspection remains available while stage parameters await the user.
export function executionKind(name, args) {
  if (/^mcp__(?:cae|hyperworks|qilan_solve)__/.test(name)) {
    if (/(?:get_|check_|probe_|read_|list_|validate_|health_gate|status)/.test(name)) return null
    return 'cae'
  }
  if (/^(?:bash|pwsh|write|edit|write_file|edit_file|apply_patch|job_output|job_kill)$/.test(name)) {
    if (/^(?:bash|pwsh)$/.test(name)) {
      const command = args?.command || args?.script || ''
      if (/^(?:pwd|ls|dir|rg|cat|Get-Content|Get-ChildItem|Test-Path)\b[^\n;&|>]*$/i.test(command)) return null
      if (/(?:hmbatch|lsdyna|run_case|auto_partition|hv_render|g14_|solve_workflow)/i.test(command)) return 'cae'
    }
    return 'write'
  }
  return null
}

export function toolSucceeded(result) {
  if (result.isError) return false
  const values = [result.value, ...(result.content || []).filter(block => block.type === 'text').map(block => block.text)]
  return !values.some(value => {
    try {
      const data = typeof value === 'string' ? JSON.parse(value) : value
      if (!data || typeof data !== 'object') return false
      if (data.isError || ['error', 'warning', 'failed', 'FAIL'].includes(data.status) || (typeof data.exitCode === 'number' && data.exitCode !== 0) || (typeof data.exit_code === 'number' && data.exit_code !== 0)) return true
      return Array.isArray(data.content) && data.content.some(block => block.type === 'text' && !toolSucceeded({ isError: false, value: block.text }))
    } catch { return false }
  })
}
