declare namespace Api {
  namespace ResearchNode {
    interface ResearchNodeItem {
      id: string
      package: PackageFiled
      history: HistoryItem[]
    }

    interface ResearchNodeField {
      name: string
      validate: string
      type: "number" | "string"
    }
  }
}
