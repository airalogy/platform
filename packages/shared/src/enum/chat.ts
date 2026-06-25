export enum ChatType {
  NORMAL = 1,
  FIELD_INPUT = 2,
  RECORDS = 3,
  VISION = 5,
  STT = 6,
}

export enum ChatModel {
  BASIC = 1,
  PLUS = 2,
  PRO = 3,
  GPT = 4,
}

export type ChatModelType = 1 | 2 | 3 | 4

export interface ChatModelConfig {
  model_type: ChatModelType
  enable_thinking?: boolean
  enable_search?: boolean
}
