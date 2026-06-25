import { useEventBus } from "@vueuse/core"

export interface ProtocolParsingError {
  message: string
  line?: number
  fileName?: string
  code?: string
  details?: Record<string, unknown>
}

export const protocolParsingEventBus = useEventBus<ProtocolParsingError>("protocol-parsing-error")

// Helper function to create protocol parsing errors
export function createProtocolError(
  message: string,
  options?: Partial<Omit<ProtocolParsingError, "message">>,
): ProtocolParsingError {
  return {
    message,
    ...options,
  }
}
