export const mockProtocolResults: Api.Search.ProtocolSearchItem[] = [
  {
    id: "1",
    name: "Carbon Nanotube Synthesis Protocol",
    title: "CNT Synthesis Using CVD Method",
    headline: "Detailed protocol for carbon nanotube synthesis using chemical vapor deposition",
    lab_uid: "materials-lab",
    project_uid: "cnt-project",
    uid: "cnt-synthesis",
    created_at: "2024-01-15T08:00:00Z",
    updated_at: "2024-01-15T08:00:00Z",
    q_headline: "Protocol details",
    a_headline: "Synthesis steps",
    content: "Full protocol content here",
  },
  {
    id: "2",
    name: "Protein Purification Protocol",
    title: "His-tagged Protein Purification",
    headline: "Standard protocol for purifying His-tagged proteins using Ni-NTA columns",
    lab_uid: "bio-lab",
    project_uid: "protein-project",
    uid: "protein-purification",
    created_at: "2024-01-10T10:00:00Z",
    updated_at: "2024-01-10T10:00:00Z",
    q_headline: "Protocol details",
    a_headline: "Purification steps",
    content: "Full protocol content here",
  },
]

export const mockRecordResults: Api.Search.RecordSearchItem[] = [
  {
    id: "1",
    title: "CNT Synthesis Experiment #1",
    headline: "First attempt at CNT synthesis using modified parameters",
    research_uid: "cnt-research-1",
    lab_uid: "materials-lab",
    project_uid: "cnt-project",
    created_at: "2024-01-16T09:00:00Z",
    updated_at: "2024-01-16T09:00:00Z",
    user: {
      id: "1",
      name: "John Doe",
      username: "johndoe",
      avatar_url: "/images/avatar_default.svg",
    },
    q_headline: "Experiment details",
    a_headline: "Results summary",
    content: "Full record content here",
  },
  {
    id: "2",
    title: "Protein Expression Run #2",
    headline: "Second batch of protein expression with optimized conditions",
    research_uid: "protein-research-1",
    lab_uid: "bio-lab",
    project_uid: "protein-project",
    created_at: "2024-01-12T11:00:00Z",
    updated_at: "2024-01-12T11:00:00Z",
    user: {
      id: "2",
      name: "Jane Smith",
      username: "janesmith",
      avatar_url: "/images/avatar_default.svg",
    },
    q_headline: "Experiment details",
    a_headline: "Results summary",
    content: "Full record content here",
  },
]

export const mockExpertiseResults: Api.Search.DiscussionSearchItem[] = [
  {
    id: "1",
    title: "Optimizing CNT Growth Temperature",
    headline: "Discussion on the effects of temperature on CNT quality",
    content: "Detailed discussion of temperature effects on CNT growth",
    tags: ["CNT", "synthesis", "optimization"],
    views_count: 156,
    answers_count: 8,
    created_at: "2024-01-14T10:00:00Z",
    updated_at: "2024-01-14T10:00:00Z",
    user: {
      id: "1",
      name: "John Doe",
      username: "johndoe",
      avatar_url: "/images/avatar_default.svg",
    },
    protocol_id: "1",
    q_headline: "Question details",
    a_headline: "Answer summary",
    user_id: "1",
    lab_id: "1",
    project_id: "1",
  },
  {
    id: "2",
    title: "Protein Stability During Purification",
    headline: "Tips for maintaining protein stability during the purification process",
    content: "Discussion of methods to prevent protein degradation",
    tags: ["protein", "purification", "stability"],
    views_count: 234,
    answers_count: 12,
    created_at: "2024-01-13T14:00:00Z",
    updated_at: "2024-01-13T14:00:00Z",
    user: {
      id: "2",
      name: "Jane Smith",
      username: "janesmith",
      avatar_url: "/images/avatar_default.svg",
    },
    protocol_id: "2",
    q_headline: "Question details",
    a_headline: "Answer summary",
    user_id: "2",
    lab_id: "1",
    project_id: "1",
  },
]

export async function getSearchResearchNode(params: {
  id: string
  type: "protocol" | "record" | "discussion"
  query: string
  page: number
  pageSize: number
  filters?: {
    dateRange?: [number, number] | null
    userIds?: string[]
  }
}): Promise<{ data: Api.GetResponse<any>, error: Error | null }> {
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 500))

  let results: any[] = []
  switch (params.type) {
    case "protocol":
      results = mockProtocolResults.filter(item =>
        item.name.toLowerCase().includes(params.query.toLowerCase())
        || item.content.toLowerCase().includes(params.query.toLowerCase()),
      )
      break
    case "record":
      results = mockRecordResults.filter((item) => {
        const matchesQuery = item.title.toLowerCase().includes(params.query.toLowerCase())
          || item.content.toLowerCase().includes(params.query.toLowerCase())

        if (!matchesQuery)
          return false

        // Apply date filter if specified
        if (params.filters?.dateRange) {
          const itemDate = new Date(item.created_at).getTime()
          if (itemDate < params.filters.dateRange[0] || itemDate > params.filters.dateRange[1]) {
            return false
          }
        }

        // Apply user filter if specified
        if (params.filters?.userIds?.length) {
          if (!params.filters.userIds.includes(item.user.id)) {
            return false
          }
        }

        return true
      })
      break
    case "discussion":
      results = mockExpertiseResults.filter(item =>
        item.title.toLowerCase().includes(params.query.toLowerCase())
        || item.content.toLowerCase().includes(params.query.toLowerCase())
        || item.tags.some(tag => tag.toLowerCase().includes(params.query.toLowerCase())),
      )
      break
  }

  // Apply pagination
  const start = (params.page - 1) * params.pageSize
  const paginatedResults = results.slice(start, start + params.pageSize)

  return {
    data: {
      data: paginatedResults,
      total_count: results.length,
    },
    error: null,
  }
}
