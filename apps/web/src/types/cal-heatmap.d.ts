declare module "cal-heatmap" {
  export default class CalHeatmap {
    paint(options?: Record<string, unknown>, plugins?: unknown): Promise<unknown>
    on(name: string, callback: (...args: unknown[]) => void): void
    destroy(): Promise<unknown>
  }
}
