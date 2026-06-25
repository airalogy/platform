import type { ProtocolModels } from "@airalogy/shared/types"
import { request } from "@/service/request"

export enum PinnedResourceType {
  Lab = 1,
  Project = 2,
  Protocol = 3,
}

export type PinnedResource =
  | Api.Lab.LabInfo
  | Api.Project.MyProjectInfo
  | ProtocolModels.ProtocolResponseInfo
  | ProtocolModels.ProjectProtocolInfo

export interface PinnedItem {
  id: number
  resource_type: PinnedResourceType
  resource_id: string
  sort_order: number
  created_at: string
  resource: PinnedResource
}

export interface PinnedItemsResponse {
  items: PinnedItem[]
  total: number
}

export interface PinnedActionResponse {
  success: boolean
}

export async function getPinnedItems() {
  return await request<PinnedItemsResponse>({
    url: "/pinned_items",
    method: "GET",
  })
}

export async function createPinnedItem(payload: {
  resource_type: PinnedResourceType
  resource_id: string
}) {
  return await request<PinnedActionResponse>({
    url: "/pinned_items",
    method: "POST",
    data: payload,
  })
}

export async function deletePinnedItem(pinnedId: number) {
  return await request<PinnedActionResponse>({
    url: `/pinned_items/${pinnedId}`,
    method: "DELETE",
  })
}

export async function reorderPinnedItems(pinnedItemIds: number[]) {
  return await request<PinnedActionResponse>({
    url: "/pinned_items/reorder",
    method: "PUT",
    data: {
      pinned_item_ids: pinnedItemIds,
    },
  })
}
