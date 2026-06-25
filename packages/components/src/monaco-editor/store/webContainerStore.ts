import type { Ref } from "vue"
import type { FileSystemItem } from "../types"
import type { FileSystemAPI, WebContainer } from "../types/fileSystem"
import { defineStore } from "pinia"
import { ref } from "vue"
import { MockFileSystem } from "../utils"

// Mock WebContainer implementation
class MockWebContainer implements Partial<WebContainer> {
  fs: FileSystemAPI
  workdir: string

  constructor(projectId: string, projectData: Ref<FileSystemItem[] | null>, rootPath: string, saveProjectData: (id: string, data: (FileSystemItem)[]) => Promise<void>) {
    this.fs = new MockFileSystem(projectId, projectData, rootPath, saveProjectData)
    this.workdir = "/"
  }

  on(event: string, listener: any): () => void {
    // Return unsubscribe function
    return () => {}
  }
}

export const useWebContainerStore = defineStore("webContainer", () => {
  const webContainerInstance = ref<WebContainer | null>(null)
  const isInitialized = ref(false)
  const url = ref("")

  function setUrl(newUrl: string) {
    url.value = newUrl
  }

  function setInitialized(newIsInitialized: boolean) {
    isInitialized.value = newIsInitialized
  }

  async function initWebContainer(projectId = "", projectData: Ref<(FileSystemItem)[] | null>, rootPath: string, saveProjectData: (id: string, data: (FileSystemItem)[]) => Promise<void>) {
    try {
      if (!isInitialized.value && !webContainerInstance.value) {
        const newWebContainerInstance = new MockWebContainer(projectId, projectData, rootPath, saveProjectData)
        // await setupWebContainerFiles(newWebContainerInstance as unknown as WebContainer, projectId, files)
        webContainerInstance.value = newWebContainerInstance as unknown as WebContainer
        isInitialized.value = true
      }
      else if (webContainerInstance.value) {
        // await setupWebContainerFiles(webContainerInstance.value, projectId, files)
        isInitialized.value = true
      }
    }
    catch (error) {
      console.error("Failed to initialize WebContainer:", error)
      throw error
    }
  }

  return {
    webContainerInstance,
    // setupWebContainerFiles,
    isInitialized,
    url,
    setUrl,
    setInitialized,
    initWebContainer,
  }
})
