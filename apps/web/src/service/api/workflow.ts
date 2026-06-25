import type { PathData, WorkflowCreatePayload, WorkflowGeneratePayload, WorkflowRequestPayload } from "@/types/workflow"
import { WorkflowStatus, WorkflowStep } from "@/enum/workflow"
import {
  normalizeWorkflowResponse,
  normalizeWorkflowStatus,
  serializeWorkflowInfoForApi,
  serializeWorkflowPathDataForApi,
} from "@/utils/workflow"
import { request } from "../request"

/**
 * defines which workflow status are valid for each workflow step
 */
const stepMap: Record<WorkflowStatus, (WorkflowStep | null | undefined)[]> = {
  [WorkflowStatus.COMPLETED]: [],
  [WorkflowStatus.RESEARCH_GOAL]: [
    WorkflowStep.ADD_NEXT_PROTOCOL,
    WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
    WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION,
    WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION,
  ],
  [WorkflowStatus.RESEARCH_STRATEGY]: [
    WorkflowStep.ADD_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
  ],
  [WorkflowStatus.END_AFTER_STRATEGY]: [
    WorkflowStep.ADD_NEXT_PROTOCOL,
    WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
    WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION,
    WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION,
  ],
  [WorkflowStatus.NEXT_PROTOCOL]: [
    WorkflowStep.ADD_NEXT_PROTOCOL,
    WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
    WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION,
    WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION,
  ],
  [WorkflowStatus.INITIAL_VALUES]: [
    WorkflowStep.ADD_NEXT_PROTOCOL,
    WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
    WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION,
    WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION,
  ],
  [WorkflowStatus.RECORD]: [
    WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
    WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION,
    WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION,
  ],
  [WorkflowStatus.END_AFTER_NEXT_PROTOCOL]: [
    WorkflowStep.ADD_NEXT_PROTOCOL,
    WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    WorkflowStep.ADD_RECORD,
    WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION,
    WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION,
  ],
  [WorkflowStatus.PHASED_CONCLUSION]: [WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION, WorkflowStep.ADD_RECORD, WorkflowStep.ADD_NEXT_PROTOCOL, WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL],
  [WorkflowStatus.FINAL_CONCLUSION]: [WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION],
}

/**
 * defines which workflow status are valid for each workflow status
 */
const statusMap: Record<WorkflowStatus, WorkflowStatus[]> = {
  [WorkflowStatus.COMPLETED]: [],
  [WorkflowStatus.RESEARCH_GOAL]: [
    WorkflowStatus.RESEARCH_STRATEGY,
    WorkflowStatus.NEXT_PROTOCOL,
  ],
  [WorkflowStatus.RESEARCH_STRATEGY]: [
    WorkflowStatus.RESEARCH_STRATEGY,
    WorkflowStatus.NEXT_PROTOCOL,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.END_AFTER_STRATEGY]: [
    WorkflowStatus.RESEARCH_STRATEGY,
    WorkflowStatus.NEXT_PROTOCOL,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.NEXT_PROTOCOL]: [
    WorkflowStatus.INITIAL_VALUES,
    WorkflowStatus.RECORD,
    WorkflowStatus.NEXT_PROTOCOL,
    WorkflowStatus.PHASED_CONCLUSION,
    WorkflowStatus.FINAL_CONCLUSION,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.INITIAL_VALUES]: [
    WorkflowStatus.INITIAL_VALUES,
    WorkflowStatus.PHASED_CONCLUSION,
    WorkflowStatus.FINAL_CONCLUSION,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.RECORD]: [
    WorkflowStatus.PHASED_CONCLUSION,
    WorkflowStatus.FINAL_CONCLUSION,
    WorkflowStatus.NEXT_PROTOCOL,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.END_AFTER_NEXT_PROTOCOL]: [
    WorkflowStatus.NEXT_PROTOCOL,
    WorkflowStatus.PHASED_CONCLUSION,
    WorkflowStatus.FINAL_CONCLUSION,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.PHASED_CONCLUSION]: [
    WorkflowStatus.PHASED_CONCLUSION,
    WorkflowStatus.NEXT_PROTOCOL,
    WorkflowStatus.FINAL_CONCLUSION,
    WorkflowStatus.COMPLETED,
  ],
  [WorkflowStatus.FINAL_CONCLUSION]: [
    WorkflowStatus.COMPLETED,
  ],
}

/**
 * validate if the status is valid for the last step
 * @param status - the status to validate
 * @param oldStep - the step to validate
 * @returns true if the step is valid for the status, false otherwise
 */
function validateStep(status: WorkflowStatus, oldStep?: WorkflowStep | null) {
  if (!oldStep) {
    return true
  }

  return stepMap[normalizeWorkflowStatus(status)]?.includes(oldStep) || false
}

/**
 * validate if the status is valid for the status
 * @param newStatus - the status to validate
 * @returns true if the status is valid, false otherwise
 */
function validateStatus(newStatus: WorkflowStatus, oldStatus: WorkflowStatus) {
  if (!oldStatus) {
    return true
  }

  return statusMap[normalizeWorkflowStatus(oldStatus)]?.includes(normalizeWorkflowStatus(newStatus)) || false
}

export async function postStartWorkflow(payload: WorkflowCreatePayload) {
  const {
    workflow_info,
    airalogy_protocol_id,
    research_goal,
  } = payload

  const response = await request<{ id: string, path_data: PathData }>({
    method: "POST",
    url: "/workflow",
    data: {
      workflow_info: serializeWorkflowInfoForApi(workflow_info),
      airalogy_protocol_id,
      research_goal,
    },
    timeout: 60 * 1000 * 2,
  })

  if (!response.data) {
    return response
  }

  return {
    ...response,
    data: {
      ...response.data,
      path_data: normalizeWorkflowResponse({
        workflow_info,
        path_data: response.data.path_data,
      } as WorkflowRequestPayload).path_data,
    },
  }
}

export async function getWorkflow(workflowId: string, showError = false) {
  const response = await request<WorkflowRequestPayload>({
    method: "GET",
    url: `/workflow/${workflowId}`,
    metadata: {
      showError,
    },
  })

  if (!response.data) {
    return response
  }

  return {
    ...response,
    data: normalizeWorkflowResponse(response.data),
  }
}

export async function postGenerateWorkflow(payload: WorkflowGeneratePayload) {
  const {
    workflowId: workflow_id,
    pathData,
    oldStatus,
    workflowInfo,
  } = payload

  const path_data = serializeWorkflowPathDataForApi(pathData, workflowInfo)
  const { path_status, steps } = path_data

  const lastStep = steps.length > 0 ? steps[steps.length - 1] : null
  const isStatusValid = validateStatus(path_status, normalizeWorkflowStatus(oldStatus))
  const isStepValid = validateStep(path_status, lastStep?.step)

  if (!isStatusValid || !isStepValid) {
    throw new Error("Invalid status or step")
  }

  const response = await request<WorkflowRequestPayload>({
    method: "POST",
    url: "/workflow/step",
    data: {
      path_data,
      workflow_id,
    },
    timeout: 60 * 1000 * 2,
  })

  if (!response.data) {
    return response
  }

  return {
    ...response,
    data: normalizeWorkflowResponse(response.data),
  }
}
