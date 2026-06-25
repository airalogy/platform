import type { UseEventBusReturn } from "@vueuse/core"

/**
 * Utility function to handle request-response pattern with event bus
 * @param eventBus - The event bus instance
 * @param requestEvent - The event name to emit for the request
 * @param responseEvent - The event name to listen for the response
 * @param payload - The payload to send with the request
 * @param timeoutMs - Timeout in milliseconds
 * @returns Promise that resolves with the response data
 */
export async function requestWithEventBus<T = any>(
  eventBus: UseEventBusReturn<any, any>,
  requestEvent: string,
  responseEvent: string,
  payload?: any,
  timeoutMs?: number,
): Promise<{ status: "error" | "success", content: T, error?: string }> {
  let timeout: ReturnType<typeof setTimeout> | null = null

  return new Promise<{ status: "error" | "success", content: T, error?: string }>((resolve, reject) => {
    const stop = eventBus.on((event, data) => {
      if (event === responseEvent) {
        resolve({ status: "success", content: data })
        stop()
        if (timeout) {
          clearTimeout(timeout)
        }
      }
    })

    eventBus.emit(requestEvent, payload)

    if (timeoutMs) {
      timeout = setTimeout(() => {
        stop()
        reject({ status: "error", error: `Timeout waiting for ${responseEvent}` })
      }, timeoutMs)
    }
  })
}
