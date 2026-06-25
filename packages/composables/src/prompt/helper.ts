import { createStorage } from "@airalogy/shared/utils"

export interface PromptState {
  promptList: string[]
}

export const LOCAL_NAME = "promptStore" as const
export const localStg = createStorage<{ [LOCAL_NAME]: PromptState }>("local")

export function getLocalPromptList(): PromptState {
  const promptStore = localStg.get(LOCAL_NAME)
  return promptStore ?? { promptList: [] }
}

export function setLocalPromptList(promptStore: PromptState): void {
  localStg.set(LOCAL_NAME, promptStore)
}
