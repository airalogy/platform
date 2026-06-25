declare namespace Api {
  namespace Discussion {
    interface CreateQuestionResponse {
      answers_count: number
      content: string
      created_at: string
      id: string
      protocol_id: string
      tags: string[]
      title: string
      updated_at: string
      user_id: string
      views_count: number
    }

    interface CreateAnswerResponse {
      comments_count: number
      content: string
      created_at: string
      id: string
      parent_id: null
      question_id: string
      updated_at: string
      user_id: string
    }

    interface QuestionItem {
      answers_count?: number
      content?: string
      created_at?: string
      id?: string
      protocol_id?: string
      tags?: string[]
      title?: string
      updated_at?: string
      user_id?: string
      starred: boolean
      stars_count: number
      upvoted: boolean
      upvotes_count: number
      user: {
        id: string
        name: string
        username: string
        avatar_url: string
      }
    }

    interface AnswerItem {
      comments_count: number
      content: string
      created_at: string
      id: string
      parent_id: null
      question_id: string
      updated_at: string
      upvoted: boolean
      upvotes_count: number
      starred: boolean
      stars_count: number
      user_id: string
      user: {
        id: string
        name: string
        username: string
        avatar_url: string
      }
      // likes_count?: number
      // is_liked?: boolean
    }

    interface QuestionHistoryItem {
      id: string
      question_id: string
      title: string
      content: string
      tags?: string[]
      created_at: string
      user: {
        id: string
        name: string
        username: string
        avatar_url: string
      }
      version: number
    }
  }
}
