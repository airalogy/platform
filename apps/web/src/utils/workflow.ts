import type {
  IProtocolWorkflow,
  PathData,
  StepData,
  StepItem,
  WorkflowProtocolInfo,
  WorkflowProtocolNode,
  WorkflowRequestPayload,
} from "@/types/workflow"
import { WorkflowStatus, WorkflowStep } from "@/enum/workflow"

export interface NormalizedWorkflowProtocol {
  protocolIndex: number
  protocolName: string
  airalogyProtocolId: string
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function toProtocolIndex(value: unknown) {
  const num = Number(value)
  if (!Number.isInteger(num) || num < 1) {
    return undefined
  }

  return num
}

function isWorkflowStatus(value?: string | null): value is WorkflowStatus {
  return Object.values(WorkflowStatus).includes((value || "") as WorkflowStatus)
}

function isWorkflowStep(value?: string | null): value is WorkflowStep {
  return Object.values(WorkflowStep).includes((value || "") as WorkflowStep)
}

function getDefaultMode(step: WorkflowStep) {
  switch (step) {
    case WorkflowStep.ADD_RESEARCH_STRATEGY:
    case WorkflowStep.ADD_NEXT_PROTOCOL:
    case WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL:
    case WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION:
    case WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION:
      return "ai"
    default:
      return "user"
  }
}

function getProtocolName(protocol: Partial<WorkflowProtocolNode>, index: number) {
  return protocol.protocol_name || protocol.airalogy_protocol_id || `Protocol ${index}`
}

function getProtocolId(protocol: Partial<WorkflowProtocolNode>, index: number) {
  return protocol.airalogy_protocol_id || String(index)
}

function buildProtocolMaps(workflow?: IProtocolWorkflow | null) {
  const protocols = normalizeWorkflowProtocols(workflow?.protocols || [])
  const indexToId = new Map<number, string>()
  const idToIndex = new Map<string, number>()

  protocols.forEach(({ protocolIndex, airalogyProtocolId }) => {
    indexToId.set(protocolIndex, airalogyProtocolId)
    if (airalogyProtocolId) {
      idToIndex.set(airalogyProtocolId, protocolIndex)
    }
  })

  return { protocols, indexToId, idToIndex }
}

function resolveProtocolIndex(
  data: Partial<StepData>,
  idToIndex: Map<string, number>,
  fallbackIndex?: number,
) {
  const protocolIndex = toProtocolIndex(data.protocol_index)
  if (protocolIndex) {
    return protocolIndex
  }

  if (data.airalogy_protocol_id && idToIndex.has(data.airalogy_protocol_id)) {
    return idToIndex.get(data.airalogy_protocol_id)
  }

  return fallbackIndex
}

function resolveProtocolId(
  data: Partial<StepData>,
  indexToId: Map<number, string>,
  fallbackIndex?: number,
) {
  if (data.airalogy_protocol_id) {
    return data.airalogy_protocol_id
  }

  const protocolIndex = toProtocolIndex(data.protocol_index) || fallbackIndex
  if (protocolIndex && indexToId.has(protocolIndex)) {
    return indexToId.get(protocolIndex)
  }

  return undefined
}

function serializeWorkflowEdges(
  edges: string[],
  idToIndex: Map<string, number>,
) {
  return edges.map((edge) => {
    const parsed = splitWorkflowEdge(edge)
    if (!parsed) {
      return edge
    }

    const sourceIndex = toProtocolIndex(parsed.source) || idToIndex.get(parsed.source)
    const targetIndex = toProtocolIndex(parsed.target) || idToIndex.get(parsed.target)

    if (!sourceIndex || !targetIndex) {
      return edge
    }

    return `${sourceIndex} ${parsed.operator} ${targetIndex}`
  }) as IProtocolWorkflow["edges"]
}

export function splitWorkflowEdge(edge: string) {
  const trimmed = edge.trim()
  const operator = trimmed.includes("<->")
    ? "<->"
    : trimmed.includes("->")
      ? "->"
      : null

  if (!operator) {
    return null
  }

  const [rawSource, rawTarget] = trimmed.split(operator)
  const source = rawSource?.trim()
  const target = rawTarget?.trim()

  if (!source || !target) {
    return null
  }

  return {
    source,
    target,
    operator,
  } as const
}

export function normalizeWorkflowStatus(status?: string | null) {
  return isWorkflowStatus(status)
    ? status
    : WorkflowStatus.RESEARCH_GOAL
}

export function normalizeWorkflowStep(step?: string | null) {
  return isWorkflowStep(step)
    ? step
    : undefined
}

export function normalizeWorkflowProtocols(protocols: Partial<WorkflowProtocolNode>[]) {
  return protocols.map((protocol, index): NormalizedWorkflowProtocol => {
    const protocolIndex = toProtocolIndex(protocol.protocol_index) || index + 1

    return {
      protocolIndex,
      protocolName: getProtocolName(protocol, protocolIndex),
      airalogyProtocolId: getProtocolId(protocol, protocolIndex),
    }
  })
}

export function normalizeWorkflowInfo(workflow?: IProtocolWorkflow | null) {
  if (!workflow) {
    return null
  }

  const { protocols, idToIndex } = buildProtocolMaps(workflow)

  return {
    ...workflow,
    protocols: protocols.map(({ protocolIndex, protocolName, airalogyProtocolId }) => ({
      protocol_index: protocolIndex,
      protocol_name: protocolName,
      airalogy_protocol_id: airalogyProtocolId,
    })),
    edges: serializeWorkflowEdges(workflow.edges || [], idToIndex),
    default_initial_protocol_index: toProtocolIndex(workflow.default_initial_protocol_index) || null,
    default_research_goal: workflow.default_research_goal || null,
    default_research_strategy: workflow.default_research_strategy || null,
  } satisfies IProtocolWorkflow
}

export function serializeWorkflowInfoForApi(workflow?: IProtocolWorkflow | null) {
  return normalizeWorkflowInfo(workflow)
}

export function normalizeWorkflowProtocolsInfo(
  protocolsInfo?: WorkflowProtocolInfo[] | null,
) {
  if (!Array.isArray(protocolsInfo)) {
    return []
  }

  return protocolsInfo.map(protocol => ({
    ...protocol,
    airalogy_protocol_id: protocol.airalogy_protocol_id || "",
    markdown: protocol.markdown || "",
  }))
}

export function serializeWorkflowPathDataForApi(
  pathData: PathData,
  workflow?: IProtocolWorkflow | null,
) {
  const { idToIndex } = buildProtocolMaps(workflow)
  let activeProtocolIndex: number | undefined

  const steps = (pathData.steps || []).map((step, index): StepItem => {
    const normalizedStep = normalizeWorkflowStep(step.step)
    if (!normalizedStep) {
      return {
        ...step,
        path_index: step.path_index ?? index,
        mode: step.mode || "user",
        data: step.data || {},
      }
    }

    const protocolIndex = resolveProtocolIndex(step.data || {}, idToIndex, activeProtocolIndex)

    if (normalizedStep === WorkflowStep.ADD_NEXT_PROTOCOL && protocolIndex) {
      activeProtocolIndex = protocolIndex
    }

    if (
      normalizedStep === WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL
      || normalizedStep === WorkflowStep.ADD_RECORD
    ) {
      activeProtocolIndex = protocolIndex || activeProtocolIndex
    }

    if (normalizedStep === WorkflowStep.ADD_RESEARCH_GOAL) {
      return {
        ...step,
        step: normalizedStep,
        path_index: step.path_index ?? index,
        mode: step.mode || getDefaultMode(normalizedStep),
        data: {
          thought: step.data?.thought || "",
          goal: step.data?.goal || "",
        },
      }
    }

    if (normalizedStep === WorkflowStep.ADD_RESEARCH_STRATEGY) {
      return {
        ...step,
        step: normalizedStep,
        path_index: step.path_index ?? index,
        mode: step.mode || getDefaultMode(normalizedStep),
        data: {
          thought: step.data?.thought || "",
          researchable: Boolean(step.data?.researchable),
          strategy: step.data?.strategy || "",
        },
      }
    }

    if (normalizedStep === WorkflowStep.ADD_NEXT_PROTOCOL) {
      return {
        ...step,
        step: normalizedStep,
        path_index: step.path_index ?? index,
        mode: step.mode || getDefaultMode(normalizedStep),
        data: {
          thought: step.data?.thought || "",
          end_path: Boolean(step.data?.end_path),
          protocol_index: step.data?.end_path ? null : protocolIndex ?? null,
        },
      }
    }

    if (normalizedStep === WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL) {
      return {
        ...step,
        step: normalizedStep,
        path_index: step.path_index ?? index,
        mode: step.mode || getDefaultMode(normalizedStep),
        data: {
          thought: step.data?.thought || "",
          values: isRecord(step.data?.values)
            ? step.data.values
            : {},
        },
      }
    }

    if (normalizedStep === WorkflowStep.ADD_RECORD) {
      return {
        ...step,
        step: normalizedStep,
        path_index: step.path_index ?? index,
        mode: step.mode || getDefaultMode(normalizedStep),
        data: {
          protocol_index: protocolIndex ?? null,
          airalogy_record_id: step.data?.airalogy_record_id || "",
          record_data: isRecord(step.data?.record_data)
            ? step.data.record_data
            : {},
        },
      }
    }

    if (
      normalizedStep === WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION
      || normalizedStep === WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION
    ) {
      return {
        ...step,
        step: normalizedStep,
        path_index: step.path_index ?? index,
        mode: step.mode || getDefaultMode(normalizedStep),
        data: {
          conclusion: step.data?.conclusion || "",
        },
      }
    }

    return {
      ...step,
      step: normalizedStep,
      path_index: step.path_index ?? index,
      mode: step.mode || getDefaultMode(normalizedStep),
      data: step.data || {},
    }
  })

  return {
    ...pathData,
    path_status: normalizeWorkflowStatus(pathData.path_status),
    final_research_conclusion: pathData.final_research_conclusion || "",
    steps,
  } satisfies PathData
}

export function normalizeWorkflowPathData(
  pathData?: PathData | null,
  workflow?: IProtocolWorkflow | null,
) {
  if (!pathData) {
    return {
      path_status: WorkflowStatus.RESEARCH_GOAL,
      researchable: false,
      final_research_conclusion: "",
      steps: [],
    } satisfies PathData
  }

  const { indexToId, idToIndex } = buildProtocolMaps(workflow)
  let activeProtocolIndex: number | undefined
  let researchable = pathData.researchable
  let finalResearchConclusion = pathData.final_research_conclusion

  const steps = (pathData.steps || []).map((step, index): StepItem => {
    const normalizedStep = normalizeWorkflowStep(step.step)
    if (!normalizedStep) {
      return {
        ...step,
        path_index: step.path_index ?? index,
        mode: step.mode || "user",
        data: step.data || {},
      }
    }

    const protocolIndex = resolveProtocolIndex(step.data || {}, idToIndex, activeProtocolIndex)
      || activeProtocolIndex
    const protocolId = resolveProtocolId(step.data || {}, indexToId, protocolIndex)

    if (normalizedStep === WorkflowStep.ADD_NEXT_PROTOCOL && protocolIndex) {
      activeProtocolIndex = protocolIndex
    }

    if (
      normalizedStep === WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL
      || normalizedStep === WorkflowStep.ADD_RECORD
    ) {
      activeProtocolIndex = protocolIndex || activeProtocolIndex
    }

    if (normalizedStep === WorkflowStep.ADD_RESEARCH_STRATEGY && typeof step.data?.researchable === "boolean") {
      researchable = step.data.researchable
    }

    if (normalizedStep === WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION && !finalResearchConclusion) {
      finalResearchConclusion = step.data?.conclusion || ""
    }

    return {
      ...step,
      step: normalizedStep,
      path_index: step.path_index ?? index,
      mode: step.mode || getDefaultMode(normalizedStep),
      data: {
        ...step.data,
        goal: step.data?.goal,
        strategy: step.data?.strategy,
        protocol_index: protocolIndex,
        airalogy_protocol_id: protocolId,
        values: isRecord(step.data?.values)
          ? step.data.values
          : {},
        airalogy_record_id: step.data?.airalogy_record_id || "",
        record_data: isRecord(step.data?.record_data)
          ? step.data.record_data
          : {},
        conclusion: step.data?.conclusion || "",
      },
    }
  })

  return {
    ...pathData,
    path_status: normalizeWorkflowStatus(pathData.path_status),
    researchable: Boolean(researchable),
    final_research_conclusion: finalResearchConclusion || "",
    steps,
  } satisfies PathData
}

export function normalizeWorkflowResponse(payload: WorkflowRequestPayload) {
  const workflowInfo = normalizeWorkflowInfo(payload.workflow_info)
  const protocolsInfo = normalizeWorkflowProtocolsInfo(payload.protocols_info || [])
  const pathData = normalizeWorkflowPathData(payload.path_data, workflowInfo)

  return {
    ...payload,
    workflow_info: workflowInfo || payload.workflow_info,
    protocols_info: protocolsInfo,
    path_data: pathData,
  } satisfies WorkflowRequestPayload
}
