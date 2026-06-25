import { useLoading } from "@/composables"
import { getProtocolInfo, fetchProtocolRecords as innerFetchProtocolRecords } from "@/service/api/project-protocols"

export function useFetchResearch() {
  const { loading, startLoading, endLoading } = useLoading()
  const route = useRoute()
  const fetchExperiment = async (id?: string) => {
    const protocolId = id || route.params.experimentId

    if (!protocolId || typeof protocolId !== "string")
      return null

    startLoading()
    const { data, error } = await getProtocolInfo(protocolId)
    endLoading()

    if (data) {
      return data
    }

    return null
  }

  return { loading, startLoading, endLoading, fetchExperiment, route }
}

export function useFetchProtocolRecords() {
  const { loading, startLoading, endLoading } = useLoading()

  const fetchProtocolRecords = async (
    protocolId: string | number,
    payload: { page: number, pageSize: number, protocolVersion?: string, number?: number, version?: string, userId?: string, q?: string } = { page: 1, pageSize: 10 },
  ) => {
    if (!protocolId)
      return null

    startLoading()

    const { page, pageSize, protocolVersion, number, version, userId, q } = payload

    const { data, error } = await innerFetchProtocolRecords(protocolId, { page, pageSize, protocolVersion, number, version, userId, q })
    endLoading()

    if (data) {
      return data
    }

    return null
  }

  return { loading, startLoading, endLoading, fetchProtocolRecords }
}
