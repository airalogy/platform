/**
 * Workflow path status used by the protocol workflow UI.
 *
 * The frontend now follows the latest AIRA workflow contract directly.
 */

export enum WorkflowStatus {
  COMPLETED = "completed",
  RESEARCH_GOAL = "waiting_for_research_goal",
  RESEARCH_STRATEGY = "waiting_for_research_strategy",
  END_AFTER_STRATEGY = "end_after_generating_research_strategy",
  NEXT_PROTOCOL = "waiting_for_next_protocol",
  END_AFTER_NEXT_PROTOCOL = "end_after_selecting_next_protocol",
  RECORD = "waiting_for_record",
  INITIAL_VALUES = "waiting_for_initial_values_for_fields_in_next_protocol",
  PHASED_CONCLUSION = "waiting_for_phased_research_conclusion",
  FINAL_CONCLUSION = "waiting_for_final_research_conclusion",
}

export enum WorkflowStep {
  ADD_RESEARCH_GOAL = "add_research_goal",
  ADD_RESEARCH_STRATEGY = "add_research_strategy",
  ADD_NEXT_PROTOCOL = "add_next_protocol",
  ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL = "add_initial_values_for_fields_in_next_protocol",
  ADD_RECORD = "add_record",
  ADD_PHASED_RESEARCH_CONCLUSION = "add_phased_research_conclusion",
  ADD_FINAL_RESEARCH_CONCLUSION = "add_final_research_conclusion",
}
