import type {
  AimdProtocolRecordData,
  AimdResourceResolverMap,
} from "@airalogy/aimd-recorder"
import type { ComputedRef, InjectionKey, Ref } from "vue"

export interface PlatformResourceResolverContext {
  resolvers: ComputedRef<AimdResourceResolverMap | undefined>
  record: ComputedRef<AimdProtocolRecordData>
  labId: Ref<string>
}

export const platformResourceResolverKey: InjectionKey<PlatformResourceResolverContext>
  = Symbol("platform-resource-resolver")
