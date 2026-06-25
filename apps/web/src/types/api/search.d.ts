declare namespace Api.Search {
  interface BaseSearchItem {
    id: string
    title: string
    headline?: string
    created_at: string
    updated_at: string

    q_headline: string
    a_headline: string
    content: string
  }

  interface ProtocolSearchItem extends BaseSearchItem {
    name: string
    lab_uid: string
    project_uid: string
    uid: string
  }

  interface RecordSearchItem extends BaseSearchItem {
    id: string
    research_uid: string
    lab_uid: string
    project_uid: string
    user: {
      id: string
      name: string
      username: string
      avatar_url: string
    }
  }

  interface DiscussionSearchItem extends BaseSearchItem {
    content: string
    tags: string[]
    views_count: number
    answers_count: number
    user: {
      id: string
      name: string
      username: string
      avatar_url: string
    }
    lab_id: string
    project_id: string
    protocol_id: string
  }
}
