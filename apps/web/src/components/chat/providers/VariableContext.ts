import type { ScopeFieldKey } from "@airalogy/aimd-core/types"
import type {
  ContextItem,
  ContextProviderDescription,
  ContextProviderExtras,
  ContextSubmenuItem,
  LoadSubmenuItemsArgs,
} from "./types"
import { requestWithEventBus } from "@airalogy/composables"
import { scopeColorRecord, scopeKeyRecord } from "@airalogy/shared/utils/schema/constants"
import { BaseContextProvider } from "./BaseContextProvider"

interface ProtocolFieldMetadata {
  title?: string
  description?: string
}

interface ProtocolFieldValuesResponse {
  field: Partial<Record<string, Record<string, unknown>>>
}

interface ProtocolFieldStructureResponse {
  field: Partial<Record<ScopeFieldKey, Record<string, ProtocolFieldMetadata>>>
}

class VariableContextProvider extends BaseContextProvider {
  static description: ContextProviderDescription = {
    title: "variable",
    displayTitle: "Variable Fields",
    description: "Type to search in this protocol",
    type: "submenu",
  }

  async getContextItems(
    query: string,
    extras: ContextProviderExtras,
  ): Promise<ContextItem[]> {
    // Assume the query is a filepath
    query = query.trim()
    const { eventBus, eventName } = extras

    try {
      const data = await requestWithEventBus<ProtocolFieldValuesResponse>(
        eventBus,
        "request:protocol/getFieldValues",
        "response:protocol/getFieldValues",
        { query },
      )

      if (data.status === "error") {
        throw new Error(data.error)
      }

      const { field } = data.content
      const items = Object.entries(field ?? {}).reduce((acc, [scope, record]) => {
        Object.entries(record ?? {}).forEach(([prop, value]) => {
          acc.push({
            // content: `${name}: ${description}`,
            content: `\`\`\`${scope}\n${prop}: ${value}\n\`\`\``,
            name: prop,
            description: scope,
          })
        })

        return acc
      }, [] as ContextItem[])

      if (eventName) {
        eventBus.emit(eventName, items)
      }

      return items
    }
    catch (error) {
      // Handle timeout error
      console.error("Failed to get context items:", error)
      return []
    }
  }

  async loadSubmenuItems(
    args: LoadSubmenuItemsArgs,
  ): Promise<ContextSubmenuItem[]> {
    // Assume the query is a filepath
    const { eventBus, eventName } = args

    try {
      const data = await requestWithEventBus<ProtocolFieldStructureResponse>(
        eventBus,
        "request:protocol/getFields",
        "response:protocol/getFields",
        {},
        0,
      )

      if (data.status === "error") {
        throw new Error(data.error)
      }

      const { field } = data.content
      const items = Object.entries(field ?? {}).reduce((acc, [scope, record]) => {
        const key = scopeKeyRecord[scope as ScopeFieldKey]
        Object.entries(record ?? {}).forEach(([prop, value]) => {
          if (prop === "__SCOPE__") {
            return
          }

          const { title, description } = value ?? {}

          acc.push({
            id: `${key}.${prop}`,
            title: prop,
            description: description ? `(${title || prop}: ${description})` : (title || prop),
            icon: h("div", { class: "text-xs font-semibold mr-1 option-field-tag", style: { color: scopeColorRecord[key] } }, key),
            label: `${key}.${prop}`,
          })
        })

        return acc
      }, [] as ContextSubmenuItem[])

      if (eventName) {
        eventBus.emit(eventName, items)
      }

      return items
    }
    catch (error) {
      // Handle timeout error
      console.error("Failed to load submenu items:", error)
      return []
    }
  }
}

export default VariableContextProvider
