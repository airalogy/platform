export interface Terms {
  stop: string
  run: string
  ask_for_help: string
  question_wizard: string
  previous: string
  next: string
  table_of_contents: string
  skip_step: string
  reverse_step: string
  sign_out: string
  settings: string
  feedback: string
  developer_mode: string
  developer_mode_description: string
  loading_wait: string
  login_or_sign_up: string
  error_traceback: string
  did_you_mean: string
  similar_frames_skipped: string
  internal_error_start: string
  error_has_been_reported: string
  try_running_code_again: string
  refresh_and_try_again: string
  try_using_different_browser: string
  give_feedback_from_menu: string
  click_for_error_details: string
  repeated_frames_description: string
  click_to_expand: string
}

export interface OutputContent {
  type: string
  text: string
  friendly?: string
  data?: any
  codeSource?: string
}
