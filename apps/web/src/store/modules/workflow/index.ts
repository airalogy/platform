import type { IProtocolWorkflow, PathData, StepData } from "@/types/workflow"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { Node } from "@vue-flow/core"
import { defineStore } from "pinia"
import { WorkflowStatus } from "../../../enum/workflow"

export interface WorkflowRecordItem {
  data: Record<string, any> | null
  status: NodeRecordStatus
  initialValue?: Record<string, any> | null
  conclusion: string
  isConclusionGenerated: boolean
  id?: string
}

export interface WorkflowModel {
  goal?: string
  strategy?: string
  researchable?: boolean
  finalResearchConclusion?: string
  record: Record<string, WorkflowRecordItem>
}

export type NodeRecordStatus = "init" | "generating" | "regenerate" | "generated" | "pending" | "done" | "error" | "deleted" | "conclusion"

export type FlowNode = StepData & { id: string, node: Node | null, initialValue: Record<string, any> | null, status: NodeRecordStatus, type: "manual" | "generated", intermediateConclusion?: string, finalConclusion?: string }
export type SelectedNode = FlowNode & { name?: string, field?: Partial<ProtocolModels.RecordInfo["data"]> | Record<string, any>, isEnd?: boolean, hideAIButton?: boolean, readonly?: boolean }

export const useProtocolWorkflowStore = defineStore("protocol-workflow", () => {
  const dataRecord = ref<Partial<Record<string, IProtocolWorkflow | null>>>({})

  const workflowNodesRecord = ref<Partial<Record<string, Node<any, any, string>[] | null>>>({})
  const flowNodesRecord = ref<Partial<Record<string, FlowNode[] | null>>>({})
  const modelRecord = ref<Partial<Record<string, WorkflowModel>>>({})
  // const packageRecord = ref<Record<string, Record<string, { model: string, assigner: string, protocol: string, hash: string }>>>({})
  // const stepsRecord = ref<Record<string, StepItem[]>>({})
  const pathRecord = ref<Partial<Record<string, PathData>>>({})
  function setData(id: string, workflow?: IProtocolWorkflow | null) {
    dataRecord.value[id] = workflow
  }
  function getData(id: string) {
    return dataRecord.value[id]
  }
  function setWorkflowNodes(id: string, nodes?: Node<any, any, string>[] | null) {
    workflowNodesRecord.value[id] = nodes
  }
  function setFlowNodes(id: string, nodes?: FlowNode[] | null) {
    flowNodesRecord.value[id] = nodes
  }

  function setModel(id: string, model?: WorkflowModel | null) {
    if (!model) {
      modelRecord.value[id] = { record: {}, finalResearchConclusion: "", goal: "", strategy: "", researchable: undefined } satisfies WorkflowModel
    }
    else {
      modelRecord.value[id] = model
    }
  }

  function getWorkflow(id?: string) {
    if (!id) {
      return null
    }

    const workflowNodes = workflowNodesRecord.value[id] || []
    if (!workflowNodesRecord.value[id]) {
      workflowNodesRecord.value[id] = workflowNodes
    }

    const flowNodes = flowNodesRecord.value[id] || []
    if (!flowNodesRecord.value[id]) {
      flowNodesRecord.value[id] = flowNodes
    }

    const data = dataRecord.value[id] || null
    if (!dataRecord.value[id]) {
      dataRecord.value[id] = data
    }

    const model = modelRecord.value[id] || { record: {}, finalResearchConclusion: "", goal: "", strategy: "", researchable: undefined } satisfies WorkflowModel

    if (!modelRecord.value[id]) {
      modelRecord.value[id] = model
    }

    const path: PathData = pathRecord.value[id] || { path_status: WorkflowStatus.RESEARCH_GOAL, researchable: false, steps: [] }

    return { data, workflowNodes, flowNodes, model, path, id: data?.id || "" }
  }

  // const getProtocolContent = useMemoize(unPackageProtocol)

  /*
  async function getPackage(researchId: string | number, protocolId: string | number) {
    try {
      const SparkMD5 = (await import("spark-md5")).default

      const nodePackage = packageRecord.value[researchId]?.[protocolId]
      if (nodePackage) {
        const spark = new SparkMD5()
        const { assigner, hash, model, protocol } = nodePackage
        if (hash) {
          const hexHash = spark.append(JSON.stringify({ assigner, model, protocol }, null, 0)).end()
          if (hexHash === hash) {
            return nodePackage
          }
        }
      }
      const res = await getDownloadPackage(researchId)
      if (res.error || !res.data) {
        return null
      }

      const result = await getProtocolContent(new File([res.data], "protocol.zip"))
      if (result) {
        const { assigner, model, protocol } = result
        const spark = new SparkMD5()
        const hash = spark.append(JSON.stringify({ assigner, model, protocol }, null, 0)).end()
        if (packageRecord.value[researchId]) {
          packageRecord.value[researchId][protocolId] = { model, assigner, protocol, hash }
        }
        else {
          packageRecord.value[researchId] = { [protocolId]: { model, assigner, protocol, hash } }
        }

        return result
      }

      return null
    }
    catch (error) {
      //
      return null
    }
  }
  */

  // function setSteps(id: string, steps?: StepItem[] | null) {
  //   stepsRecord.value[id] = steps || []
  // }

  // function getSteps(id: string) {
  //   return stepsRecord.value[id] || null
  // }
  // function setStatus(id: string, status: WorkflowStatus) {
  //   pathRecord.value[id] = status
  // }
  function setPath(id: string, path: PathData) {
    pathRecord.value[id] = path
  }

  function getPath(id: string) {
    return pathRecord.value[id] || null
  }

  function moveWorkflow(id: string, newId: string) {
    dataRecord.value[newId] = dataRecord.value[id]
    delete dataRecord.value[id]
    workflowNodesRecord.value[newId] = workflowNodesRecord.value[id]
    delete workflowNodesRecord.value[id]
    flowNodesRecord.value[newId] = flowNodesRecord.value[id]
    delete flowNodesRecord.value[id]
    modelRecord.value[newId] = modelRecord.value[id]
    delete modelRecord.value[id]
    pathRecord.value[newId] = pathRecord.value[id]
    delete pathRecord.value[id]
  }

  return {
    dataRecord,
    workflowNodesRecord,
    flowNodesRecord,
    modelRecord,
    // packageRecord,
    // stepsRecord,
    setData,
    getData,
    setWorkflowNodes,
    setFlowNodes,
    setModel,
    getWorkflow,
    // getPackage,
    // setSteps,
    // getSteps,
    moveWorkflow,
    setPath,
    getPath,
    pathRecord,
  }
}, {
  persist: true,
})
