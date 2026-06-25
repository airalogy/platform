import { request } from "@/service/request"

export async function getActivities(payload: {
  userId: string
  page: number
  pageSize: number
}) {
  const { page = 1, pageSize = 10, userId } = payload
  if (!userId) {
    throw new Error("userId is required")
  }

  return await request<Record<"records" | "labs" | "projects" | "groups", Api.Activity.ActivityItem[]>>({
    method: "GET",
    url: `/users/${userId}/activities`,
    params: { page, page_size: pageSize },
  })
}
