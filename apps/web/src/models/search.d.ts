declare namespace Api {
  namespace Search {
    interface DiscussionSearchItem {
      a_headline: string | null
      answers_count: number
      content: string
      created_at: string
      headline: string
      id: string
      q_headline: string
      protocol_id: string
      tags: string[]
      title: string
      updated_at: string
      user_id: string
      views_count: number
    }

    interface SearchItem {
      name: string
      value: string
    }
  }
}
