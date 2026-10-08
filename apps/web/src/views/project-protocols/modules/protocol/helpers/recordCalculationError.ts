/** A local, user-facing calculation error, distinct from transport failures. */
export class RecordCalculationError extends Error {
  constructor(message: string, public field?: string) {
    super(message)
    this.name = "RecordCalculationError"
  }
}
