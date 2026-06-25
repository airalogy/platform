import type { RouteLocationRaw } from "vue-router"
import type { WorkflowStatus, WorkflowStep } from "../enum/workflow"

export interface WorkflowCreatePayload {
  workflow_info: IProtocolWorkflow
  airalogy_protocol_id: string
  research_goal: string
}
export interface WorkflowGeneratePayload {
  oldStatus: WorkflowStatus
  pathData: PathData
  workflowId: string
  workflowInfo?: IProtocolWorkflow | null
  [property: string]: any
}

export interface WorkflowRequestPayload {
  protocols_info?: WorkflowProtocolInfo[]
  workflow_info: IProtocolWorkflow
  path_data: PathData

  [property: string]: any
}

export interface PathData {
  path_status: WorkflowStatus
  researchable?: boolean
  steps: StepItem[]
  final_research_conclusion?: string
}

export interface PathConfig {
  allow_research_goal_adjustment: boolean
  allow_research_strategy_adjustment: boolean
  [property: string]: any
}

export interface StepItem {
  data: StepData

  step: WorkflowStep
  path_index?: number
  mode?: "ai" | "user"
}

export interface StepData {
  goal?: string
  strategy?: string
  end_path?: boolean
  conclusion?: string
  values?: Record<string, any>
  protocol_index?: number | null
  airalogy_protocol_id?: string
  airalogy_record_id?: string
  record_data?: Record<string, any>
  researchable?: boolean
  thought?: string
  [property: string]: any
}

export interface WorkflowProtocolInfo {
  assigner: null | string
  field_json_schema: any
  model: string | null
  markdown?: string
  airalogy_protocol_id: string
  [property: string]: any
}

export interface IProtocolWorkflow {
  id: string
  title: string
  protocols: WorkflowProtocolNode[]
  edges: Edge[]
  logic: Logic
  default_research_goal?: string | null
  default_research_strategy?: string | null
  default_initial_protocol_index?: number | null
  redirectRoute?: RouteLocationRaw
}

export interface WorkflowProtocolNode {
  protocol_index: number
  protocol_name: string
  airalogy_protocol_id: string
  [property: string]: any
}

type Edge =
  | `${number} -> ${number}`
  | `${number} <-> ${number}`

type Logic = string | string[]
