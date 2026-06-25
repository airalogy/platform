import type { BaseContextProvider } from "./BaseContextProvider"
import type { ContextProviderName } from "./types"
import DiscussionProvider from "./DiscussionProvider"
import ProtocolProvider from "./ProtocolProvider"
import RecordProvider from "./RecordProvider"
import VariableContextProvider from "./VariableContext"

/**
 * Note: We are currently omitting the following providers due to bugs:
 * - `CodeOutlineContextProvider`
 * - `CodeHighlightsContextProvider`
 *
 * See this issue for details: https://github.com/continuedev/continue/issues/1365
 */
const defaultProviders: (typeof BaseContextProvider)[] = [
  VariableContextProvider,
  DiscussionProvider,
  ProtocolProvider,
  RecordProvider,
]

export function contextProviderClassFromName(
  name: ContextProviderName,
): typeof BaseContextProvider | undefined {
  return defaultProviders.find(cls => cls.description.title === name)
}
