import type { ResearchInventoryReservationOption } from "@/service/api/resources"
import type {
  AimdProtocolRecordData,
  AimdResourceResolverMap,
} from "@airalogy/aimd-recorder"
import type { ComputedRef, InjectionKey, Ref } from "vue"

export interface PlatformResourceResolverContext {
  resolvers: ComputedRef<AimdResourceResolverMap | undefined>
  record: ComputedRef<AimdProtocolRecordData>
  labId: Ref<string>
  projectId: Ref<string>
  inventoryReservations: Ref<Record<string, ResearchInventoryReservationOption[]>>
}

export const platformResourceResolverKey: InjectionKey<PlatformResourceResolverContext>
  = Symbol("platform-resource-resolver")
