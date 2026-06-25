export const fieldTypeRecord = {
  number: "info",
  string: "warning",
} as const

export const labTypeRecord = {
  private: 1,
  public: 2,
} as const
export type ILabTypeProps = keyof typeof labTypeRecord
export type ILabValue = (typeof labTypeRecord)[ILabTypeProps]
