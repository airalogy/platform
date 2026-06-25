import type { ContextProviderName } from "../providers/types"
import { nanoid } from "nanoid"
import { contextProviderClassFromName } from "../providers"
import { chatStorage, LOCAL_CHAT_STORAGE_NAME } from "../utils/storage"

export interface ContextProviderWithParams {
  name: ContextProviderName
  params: { [key: string]: any }
}

export interface SlashCommandDescription {
  name: string
  description: string
  params?: { [key: string]: any }
}

export interface CustomCommand {
  name: string
  prompt: string
  description: string
}

export const defaultContextProviders: Partial<Chat.ContextProviderWithParams>[] = [
  { name: "variable", id: "variable", params: {} },
  { name: "discussion", id: "discussion", params: {} },
  { name: "protocol", id: "protocol", params: {} },
  { name: "record", id: "record", params: {} },
]

export const defaultSlashCommands: SlashCommandDescription[] = [
  {
    name: "WithoutContext",
    description: "Send message without context",
  },
]

export const defaultConfig: Chat.ChatConfig = {
  customCommands: [
    {
      name: "test",
      prompt:
        "{{{ input }}}\n\nWrite a comprehensive set of protocol tests for the selected code. It should setup, run tests that check for correctness including important edge cases, and teardown. Ensure that the tests are complete and sophisticated. Give the tests just as chat output, don't edit any file.",
      description: "Write protocol tests for highlighted code",
    },
  ],
  // tabAutocompleteModel: {
  //   title: "Starcoder2 3b",
  //   provider: "ollama",
  //   model: "starcoder2:3b",
  // },
  contextProviders: defaultContextProviders.map((provider) => {
    const ProviderClass = contextProviderClassFromName(provider.name as ContextProviderName) as any
    if (!ProviderClass) {
      console.error(`Context provider class not found for name: ${provider.name}`)
      return null
    }
    return new ProviderClass(provider.params)
  }).filter(Boolean),
  slashCommands: defaultSlashCommands.map(cmd => ({
    title: `/${cmd.name}`,
    description: cmd.description,
    type: "slashCommand" as Chat.ComboBoxItemType,
  })),
}

export function defaultState(setActive = true): Chat.ChatState {
  return {
    active: setActive ? nanoid() : null,
    history: [],
    session: [],
    isInit: true,
  }
}

export function getLocalState(): Chat.ChatState {
  const localState = chatStorage.get(LOCAL_CHAT_STORAGE_NAME) || {}
  return { ...defaultState(), ...localState }
}

export function setLocalState(state: Chat.ChatState) {
  chatStorage.set(LOCAL_CHAT_STORAGE_NAME, state)
}
