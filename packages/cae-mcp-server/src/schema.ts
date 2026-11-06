import { z } from 'zod'

export function zodToJsonSchema(schema: z.ZodTypeAny): Record<string, unknown> {
  const description = schema.description
  let inner = schema
  while (inner instanceof z.ZodOptional || inner instanceof z.ZodDefault) inner = inner._def.innerType
  let result: Record<string, unknown>
  if (inner instanceof z.ZodObject) {
    const properties: Record<string, unknown> = {}
    const required: string[] = []
    for (const [key, value] of Object.entries(inner.shape)) {
      const field = value as z.ZodTypeAny
      properties[key] = zodToJsonSchema(field)
      if (!field.isOptional()) required.push(key)
    }
    result = { type: 'object', properties, required }
  } else if (inner instanceof z.ZodEnum) result = { type: 'string', enum: inner.options }
  else if (inner instanceof z.ZodNumber) {
    result = { type: inner.isInt ? 'integer' : 'number' }
    if (inner.minValue !== null) result.minimum = inner.minValue
    if (inner.maxValue !== null) result.maximum = inner.maxValue
  } else if (inner instanceof z.ZodBoolean) result = { type: 'boolean' }
  else if (inner instanceof z.ZodArray) result = { type: 'array', items: zodToJsonSchema(inner.element) }
  else result = { type: 'string' }
  if (description) result.description = description
  return result
}
