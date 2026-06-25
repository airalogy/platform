declare namespace Api {
  interface GetResponse<T> {
    total_count: number
    data: T[]
  }

  type GetResponseWithCount<K extends string, T> = {
    total_count: number
  } & { [key in K]: T }

  interface ErrorResponse {
    detail: string
  }

  interface ActionSuccessResponse {
    message: string
  }
}
