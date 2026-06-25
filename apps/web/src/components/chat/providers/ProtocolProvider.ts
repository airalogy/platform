import type { ContextItem, ContextProviderDescription, ContextProviderExtras, ContextSubmenuItem, LoadSubmenuItemsArgs } from "./types"
import { BaseContextProvider } from "./BaseContextProvider"

export class ProtocolProvider extends BaseContextProvider {
  static description: ContextProviderDescription = {
    title: "protocol",
    displayTitle: "Protocol",
    description: "Search and reference Protocols",
    type: "submenu",
  }

  async getContextItems(
    query: string,
    extras: ContextProviderExtras,
  ): Promise<ContextItem[]> {
    // Here you would implement the actual protocol search logic
    // For now, returning a mock implementation
    return [{
      content: "protocol",
      name: "protocol",
      description: "protocol",
    }]
    // const protocols = await this.searchProtocols(query)

    // return protocols.map(protocol => ({
    //   content: JSON.stringify(createProtocolInjectionMessages([protocol.id])),
    //   name: protocol.title,
    //   description: protocol.description,
    // }))
  }

  async loadSubmenuItems(args: LoadSubmenuItemsArgs): Promise<ContextSubmenuItem[]> {
    return [{ id: "123", title: "123", description: "123" }]
  }

  private async searchProtocols(query: string): Promise<Array<{ id: string, title: string, description: string }>> {
    // Implement actual protocol search logic here
    // This should connect to your backend API to search protocols
    return [{ id: "123", title: "123", description: "123" }]
  }
}

export default ProtocolProvider
