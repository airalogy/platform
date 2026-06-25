import { request } from "@/service/request"

export enum SortEnum {
  StarsCount = "stars_count",
  ForksCount = "forks_count",
  UpdatedAt = "updated_at",
}

/**
 * Get protocols from the hub
 * @param payload Optional parameters for pagination
 * @returns List of protocols
 */
export async function getFetchHubProtocols(payload: {
  page?: number
  pageSize?: number
  name?: string
  q?: string
  sort?: SortEnum
} = {}, requestId?: string) {
  const { page = 1, pageSize = 10, name, q, sort } = payload

  const { data } = await request<
    Api.GetResponseWithCount<"protocols", Api.Hub.Protocol[]>
  >({
    url: "/hub",
    method: "GET",
    params: {
      page,
      page_size: pageSize,
      name,
      q,
      sorted_by: sort,
    },
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}
