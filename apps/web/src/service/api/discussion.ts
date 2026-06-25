import { request } from "../request"

export async function getQuestions(payload: {
  id: string | number
  page?: number
  pageSize?: number
  query?: string
}, requestId?: string) {
  const { id, page = 1, pageSize = 10, query } = payload

  const { data } = await request<{ questions: Api.Discussion.QuestionItem[], total_count: number }>({
    url: "/questions",
    params: {
      protocol_id: id,
      q: query,
      page,
      page_size: pageSize,
    },
    method: "GET",
    metadata: {
      showError: false,
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postAddQuestion(payload: {
  protocol_id: string
  title: string
  content: string
  tags?: string[]
}) {
  const { content, protocol_id, title, tags } = payload

  const { data } = await request<Api.Discussion.CreateQuestionResponse>({
    url: "/questions",
    method: "POST",
    data: {
      content,
      protocol_id,
      title,
      tags,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function putChangeQuestion(payload: {
  uuid: string
  title?: string
  content?: string
  tags?: string[]
}) {
  const { content, uuid, title, tags } = payload

  const { data } = await request<object>({
    url: `/questions/${uuid}`,
    method: "PUT",
    data: {
      content,
      title,
      tags,
    },
  })

  if (data) {
    return true
  }

  return false
}

export async function deleteQuestion(uuid: string) {
  if (!uuid) {
    throw new Error("question uuid is required")
  }

  const { data } = await request<{ message: "ok" }>({
    url: `/questions/${uuid}`,
    method: "DELETE",
  })

  if (data) {
    return true
  }

  return false
}

export async function getQuestionDetail(uuid: string, requestId?: string) {
  if (!uuid) {
    throw new Error("question uuid is required")
  }

  const { data } = await request<Api.Discussion.QuestionItem>({
    url: `/questions/${uuid}`,
    method: "GET",
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function getAnswers(payload: {
  questionId: string | number
  answerId?: string | number
  page?: number
  pageSize?: number
  sortBy?: string
}) {
  const { questionId, answerId, page = 1, pageSize = 10, sortBy = "upvotes" } = payload

  const { data } = await request<Api.GetResponseWithCount<"answers", Api.Discussion.AnswerItem[]>>(
    {
      url: "/answers",
      params: {
        question_id: questionId,
        parent_id: answerId,
        page,
        page_size: pageSize,
        sort_by: sortBy,
      },
      method: "GET",
    },
  )

  if (data) {
    return data
  }

  return null
}

export async function postAddAnswer(payload: {
  questionId: string | number
  answerId?: string | number
  content: string
}) {
  const { content, questionId, answerId } = payload

  const { data } = await request<object>({
    url: "/answers",
    method: "POST",
    data: {
      content,
      question_id: questionId,
      parent_id: answerId,
    },
  })

  if (data) {
    return true
  }

  return false
}

export async function putChangeAnswer(payload: { id: string, content?: string }) {
  const { content, id } = payload

  const { data } = await request<object>({
    url: `/answers/${id}`,
    method: "PUT",
    data: {
      content,
    },
  })

  if (data) {
    return true
  }

  return false
}

export async function deleteAnswer(id: string) {
  if (!id) {
    throw new Error("answer id is required")
  }

  const { data } = await request<object>({
    url: `/answers/${id}`,
    method: "DELETE",
  })

  if (data) {
    return true
  }

  return false
}

export async function postUpvoteAnswer(id: string) {
  if (!id) {
    throw new Error("answer id is required")
  }

  const { data } = await request<{ upvotes_count: number }>({
    url: `/answers/${id}/upvote`,
    method: "POST",
    data: {
      up: true,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postCancelUpvoteAnswer(id: string) {
  if (!id) {
    throw new Error("answer id is required")
  }

  const { data } = await request<{ upvotes_count: number }>({
    url: `/answers/${id}/upvote`,
    method: "POST",
    data: {
      up: false,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postSearchExpertise(payload: {
  protocolId: string | number
  query: string
}) {
  const { protocolId, query } = payload

  const { data } = await request<Api.GetResponse<Api.Discussion.QuestionItem[]>>({
    url: "/search",
    method: "POST",
    data: {
      protocol_id: protocolId,
      type: "question",
      q: query,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postStarAnswer(payload: {
  answerId: string
  projectId: string
  protocolId: string
}) {
  const { answerId, projectId, protocolId } = payload

  const { data } = await request<object>({
    url: `/answers/${answerId}/star`,
    method: "POST",
    data: {
      project_id: projectId,
      protocol_id: protocolId,
    },
  })

  if (data) {
    return true
  }

  return false
}

export async function postStarQuestion(payload: {
  questionId: string
  projectId: string
  protocolId: string
}) {
  const { questionId, projectId, protocolId } = payload

  const { data } = await request<object>({
    url: `/questions/${questionId}/star`,
    method: "POST",
    data: {
      project_id: projectId,
      protocol_id: protocolId,
    },
  })

  if (data) {
    return true
  }

  return false
}

export async function postUpvoteQuestion(id: string) {
  if (!id) {
    throw new Error("question id is required")
  }

  const { data } = await request<{ upvotes_count: number }>({
    url: `/questions/${id}/upvote`,
    method: "POST",
    data: {
      up: true,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postCancelUpvoteQuestion(id: string) {
  if (!id) {
    throw new Error("question id is required")
  }

  const { data } = await request<{ upvotes_count: number }>({
    url: `/questions/${id}/upvote`,
    method: "POST",
    data: {
      up: false,
    },
  })

  if (data) {
    return data
  }

  return null
}
