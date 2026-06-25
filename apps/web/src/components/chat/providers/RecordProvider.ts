import type { ContextItem, ContextProviderDescription, ContextProviderExtras } from "./types"
import { createRecordInjectionMessages } from "@/utils/chat"
import { BaseContextProvider } from "./BaseContextProvider"

export class RecordProvider extends BaseContextProvider {
  static description: ContextProviderDescription = {
    title: "record",
    displayTitle: "Record",
    description: "Search and reference Records",
    type: "submenu",
  }

  async getContextItems(
    query: string,
    extras: ContextProviderExtras,
  ): Promise<ContextItem[]> {
    // Here you would implement the actual record search logic
    // For now, returning a mock implementation
    const records = await this.searchRecords(query)

    return records.map(record => ({
      content: JSON.stringify(createRecordInjectionMessages([record.id])),
      name: record.title,
      description: record.description,
      icon: "i-carbon-data-table",
    }))
  }

  private async searchRecords(query: string): Promise<Array<{ id: string, title: string, description: string }>> {
    // Implement actual record search logic here
    // This should connect to your backend API to search records
    return []
  }
}

export default RecordProvider
