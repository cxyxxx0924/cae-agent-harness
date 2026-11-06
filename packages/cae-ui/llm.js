import { createRequire } from 'node:module'

const dshRequire = createRequire(import.meta.resolve('@deepseek-ai/dsh/package.json'))
const { Config, inject, apply: applyPiAi } = await import(dshRequire.resolve('@deepseek-ai/dsh-llm-pi-ai'))

export { Config, inject }

function highDefault(model) {
  if (!model.reasoning?.efforts.some(effort => effort.id === 'high')) return model
  return { ...model, reasoning: { ...model.reasoning, defaultEffort: 'high' } }
}

function withHighDefaults(adapter) {
  return new Proxy(adapter, {
    get(target, property) {
      if (property === 'resolveModel') return async (...args) => highDefault(await target.resolveModel(...args))
      if (property === 'prepareCall') return async (...args) => {
        const prepared = await target.prepareCall(...args)
        return { ...prepared, model: highDefault(prepared.model) }
      }
      const value = Reflect.get(target, property)
      return typeof value === 'function' ? value.bind(target) : value
    },
  })
}

export function apply(ctx, config) {
  if (process.env.CAE_MODELS_CONFIGURED === '0') return
  const llm = ctx.llm
  const scoped = ctx.extend({
    llm: new Proxy(llm, {
      get(target, property) {
        if (property === 'registerAdapter') return (providers, adapter) => target.registerAdapter(providers, withHighDefaults(adapter))
        const value = Reflect.get(target, property)
        return typeof value === 'function' ? value.bind(target) : value
      },
    }),
  })
  applyPiAi(scoped, config)
}
