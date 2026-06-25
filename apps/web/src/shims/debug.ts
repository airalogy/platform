type DebugLogger = ((...args: unknown[]) => void) & {
  namespace: string
  enabled: boolean
  extend: (namespace: string) => DebugLogger
  destroy: () => boolean
}

type DebugFactory = ((namespace: string) => DebugLogger) & {
  debug: DebugFactory
  default: DebugFactory
  coerce: (value: unknown) => unknown
  disable: () => string
  enable: (namespaces: string) => void
  enabled: (namespace: string) => boolean
  humanize: (value: number) => string
  destroy: () => boolean
  names: RegExp[]
  skips: RegExp[]
  formatters: Record<string, (value: unknown) => string>
}

function createLogger(namespace: string): DebugLogger {
  const logger = (() => {}) as DebugLogger

  logger.namespace = namespace
  logger.enabled = false
  logger.extend = childNamespace => createLogger(`${namespace}:${childNamespace}`)
  logger.destroy = () => false

  return logger
}

const createDebug = ((namespace: string) => createLogger(namespace)) as DebugFactory

createDebug.debug = createDebug
createDebug.default = createDebug
createDebug.coerce = value => value
createDebug.disable = () => ""
createDebug.enable = () => {}
createDebug.enabled = () => false
createDebug.humanize = value => `${value}ms`
createDebug.destroy = () => false
createDebug.names = []
createDebug.skips = []
createDebug.formatters = {}

export const debug = createDebug
export const coerce = createDebug.coerce
export const disable = createDebug.disable
export const enable = createDebug.enable
export const enabled = createDebug.enabled
export const humanize = createDebug.humanize
export const destroy = createDebug.destroy
export const names = createDebug.names
export const skips = createDebug.skips
export const formatters = createDebug.formatters
export default createDebug
