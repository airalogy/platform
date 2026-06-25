import type { EventBusKey } from "@vueuse/core"

export const fieldEventKey: EventBusKey<{ name: "field-event" }> = Symbol("symbol-field-event-key")
export const protocolKey: EventBusKey<{ name: "protocol-key" }> = Symbol("symbol-protocol-key")

export const draftEventKey: EventBusKey<{ name: "draft-event" }> = Symbol("draft-event-key")

export const reportEventKey: EventBusKey<{ name: "report-event" }> = Symbol("symbol-report-event-key")

export const bubbleMenuEventKey: EventBusKey<{ name: "bubble-menu-event" }> = Symbol("symbol-bubble-menu-event-key")
