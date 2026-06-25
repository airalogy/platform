import type { AimdNode, RenderContext } from "@airalogy/aimd-core/types"
import type { VueRendererOptions } from "@airalogy/aimd-renderer"
import type { IAIMDItemProps } from "../types/aimd-types"
import { h } from "vue"
import AimdFigure from "../components/aimd-figure.vue"
import AIMDItem from "../components/aimd-item.vue"
import AIMDTag from "../components/aimd-tag.vue"
import CheckRenderer from "../components/check-renderer.vue"
import StepRenderer from "../components/step-renderer.vue"

// Map short scope codes to display names
const scopeDisplayMap: Record<string, string> = {
  var: "var",
  step: "step",
  check: "check",
  var_table: "table",
}

type AimdRendererMap = NonNullable<VueRendererOptions["aimdRenderers"]>
export type AimdComponentRenderer = AimdRendererMap[string]

function getContextFieldValue(
  ctx: RenderContext,
  item: Pick<IAIMDItemProps, "scope" | "prop">,
): unknown {
  const scopeValue = ctx.value?.[item.scope]
  if (!scopeValue || typeof scopeValue !== "object") {
    return undefined
  }

  const fieldValue = (scopeValue as Record<string, unknown>)[item.prop]
  if (!fieldValue || typeof fieldValue !== "object" || !("value" in fieldValue)) {
    return undefined
  }

  return (fieldValue as { value?: unknown }).value
}

/**
 * Base node interface for getPropsFromNode
 */
interface BaseNode {
  id: string
  scope: string
  type?: string
}

/**
 * Get props from variableList by node info
 * Migrated from tokenRenderer.ts
 */
export function getPropsFromNode(node: BaseNode, variableList: IAIMDItemProps[]): IAIMDItemProps | null {
  const { id, scope, type } = node
  return variableList.find(
    it => it.scope === scope && it.prop === id && (!type || it.type === type),
  ) || null
}

export interface UseAimdRenderersOptions {
  /**
   * Get props for a field from the variableList
   */
  getTokenProps: (node: { id: string, scope: string, type?: string }) => IAIMDItemProps | null
  /**
   * Mode: edit or preview
   */
  mode: "edit" | "preview" | "report"
  /**
   * Function to resolve file paths (e.g., relative paths) to URLs
   */
  resolveFile?: (src: string) => Promise<{ url: string } | null> | null
}

/**
 * Render preview tag for AIMD field
 * Uses aimd-field classes from @airalogy/aimd-recorder/styles
 */
function renderPreviewTag(
  scope: string,
  name: string,
  columns?: string[],
): ReturnType<typeof h> {
  const scopeKey = scopeDisplayMap[scope] || scope

  // var_table: render tag with table preview inside
  if (scope === "var_table" || scope === "rt") {
    const children: VNode[] = [
      h("div", { class: "aimd-field__header" }, [
        h("span", { class: "aimd-field__scope" }, "TABLE"),
        h("span", { class: "aimd-field__name" }, name),
      ]),
    ]
    // Add table preview inside the container
    if (columns && columns.length > 0) {
      children.push(
        h("table", { class: "aimd-field__table-preview" }, [
          h("thead", [
            h("tr", columns.map(col => h("th", col))),
          ]),
          h("tbody", [
            h("tr", columns.map(() => h("td", "..."))),
          ]),
        ]),
      )
    }
    return h("div", {
      "class": "aimd-field aimd-field--var-table",
      "data-aimd-type": "var_table",
      "data-aimd-name": name,
    }, children)
  }

  // Use aimd-field style (light blue background)
  return h(
    "span",
    {
      "class": "aimd-field aimd-field--var",
      "data-aimd-type": "var",
      "data-aimd-name": name,
    },
    [
      h("span", { class: "aimd-field__scope" }, scopeKey.toUpperCase()),
      h("span", { class: "aimd-field__name" }, name),
    ],
  )
}

/**
 * Create AIMD renderers for Vue components
 */
export function useAimdRenderers(options: UseAimdRenderersOptions): Record<string, AimdComponentRenderer> {
  const { getTokenProps, mode, resolveFile } = options

  return {
    var: (node: AimdNode, ctx: RenderContext) => {
      const { id, scope } = node
      const isPreview = mode === "preview"

      if (isPreview) {
        return renderPreviewTag("var", id)
      }

      // Edit mode - render AIMDItem component
      const item = getTokenProps({ id, scope: "research_variable" })
      if (!item) {
        // Fallback to simple tag if no item props
        return renderPreviewTag("var", id)
      }

      // Sync model value from ctx.value (external fieldModel) if available
      // This ensures left panel changes are reflected in the AIMD preview
      const itemWithSyncedValue = { ...item }
      if (ctx.value && item.scope && item.prop) {
        const externalValue = getContextFieldValue(ctx, item)
        if (externalValue !== undefined && itemWithSyncedValue.model) {
          itemWithSyncedValue.model = { ...itemWithSyncedValue.model, value: externalValue }
        }
      }

      return h("span", {
        "class": "aimd-field-wrapper aimd-field-wrapper--inline",
        "id": `${scope}-${id}`,
        "data-has-variable": "true",
      }, [h(AIMDItem, itemWithSyncedValue)])
    },

    var_table: (node: AimdNode, _ctx: RenderContext) => {
      const { id } = node
      const columns = "columns" in node ? (node.columns as string[]) : []
      const isPreview = mode === "preview"

      if (isPreview) {
        return renderPreviewTag("var_table", id, columns)
      }

      // Edit mode - render AIMDTag component
      const item = getTokenProps({ id, scope: "research_variable" })

      // Fallback to preview tag if no item props found in variableList
      if (!item) {
        return renderPreviewTag("var_table", id, columns)
      }

      // Ensure info.subvars is set from node columns if not already present
      if (columns.length > 0 && (!item.info?.subvars || item.info.subvars.length === 0)) {
        item.info = { ...item.info, subvars: columns, name: id }
      }

      return h(AIMDTag, item)
    },

    step: (node: AimdNode, ctx: RenderContext) => {
      const { id } = node
      const isPreview = mode === "preview"

      // Get step number from node if available
      const stepNum = "step" in node ? String(node.step) : "1"
      // Get check property from node (indicates if step has checkbox)
      const hasCheck = "check" in node ? Boolean(node.check) : false

      if (isPreview) {
        // Preview mode: render as "Step N >" format using research-step__sequence style
        return h("span", { class: "research-step__sequence" }, `Step ${stepNum} >`)
      }

      // Edit mode - render StepRenderer component
      const checkItem = hasCheck ? getTokenProps({ id, scope: "research_step", type: "rs-check" }) : null
      const annotationItem = getTokenProps({ id, scope: "research_step", type: "rs-annotation" })

      // Sync model value from ctx.value if available
      const syncItem = (sourceItem: any) => {
        if (!sourceItem || !ctx.value)
          return sourceItem
        const externalValue = getContextFieldValue(ctx, sourceItem)
        if (externalValue !== undefined && sourceItem.model) {
          return { ...sourceItem, model: { ...sourceItem.model, value: externalValue } }
        }
        return sourceItem
      }

      return h(StepRenderer, {
        item: syncItem(checkItem),
        annotationItem: syncItem(annotationItem),
        name: id,
        step: stepNum,
        check: hasCheck,
        content: [],
      })
    },

    check: (node: AimdNode, ctx: RenderContext) => {
      const { id } = node
      const label = "label" in node ? (node.label as string) : id
      const isPreview = mode === "preview"

      if (isPreview) {
        // Preview mode: render with checkbox (disabled)
        return h("label", {
          "class": "aimd-field aimd-field--check",
          "data-aimd-type": "check",
          "data-aimd-name": id,
          "id": `rc-${id}`,
        }, [
          h("input", {
            type: "checkbox",
            disabled: true,
            class: "aimd-checkbox",
          }),
          h("span", { class: "aimd-field__label" }, label),
        ])
      }

      // Edit mode - render CheckRenderer component
      const item = getTokenProps({ id, scope: "research_check" })
      const annotationItem = getTokenProps({ id, scope: "research_check", type: "rc-annotation" })

      // Sync model value from ctx.value if available
      const syncItem = (sourceItem: any) => {
        if (!sourceItem || !ctx.value)
          return sourceItem
        const externalValue = getContextFieldValue(ctx, sourceItem)
        if (externalValue !== undefined && sourceItem.model) {
          return { ...sourceItem, model: { ...sourceItem.model, value: externalValue } }
        }
        return sourceItem
      }

      return h(CheckRenderer, {
        item: syncItem(item),
        annotationItem: syncItem(annotationItem),
        name: id,
        content: [],
      })
    },

    ref_step: (node: AimdNode, _ctx: RenderContext) => {
      const refTarget = "refTarget" in node ? (node.refTarget as string) : node.id

      // Both preview and edit mode: render as blockquote-style reference with step sequence format
      return h("span", {
        "class": "aimd-ref aimd-ref--step",
        "data-aimd-type": "ref_step",
        "data-aimd-ref": refTarget,
      }, [
        h("span", { class: "aimd-ref__content" }, [
          h("span", { class: "research-step__sequence" }, `Step ${refTarget}`),
        ]),
      ])
    },

    ref_var: (node: AimdNode, _ctx: RenderContext) => {
      const refTarget = "refTarget" in node ? (node.refTarget as string) : node.id
      const isPreview = mode === "preview"

      // Get variable info from getTokenProps
      const varItem = getTokenProps({ id: refTarget, scope: "research_variable" })

      if (isPreview) {
        // Preview mode: render as blockquote-style reference with field content
        return h("span", {
          "class": "aimd-ref aimd-ref--var",
          "data-aimd-type": "ref_var",
          "data-aimd-ref": refTarget,
        }, [
          h("span", { class: "aimd-ref__content" }, [
            h("span", { class: "aimd-field aimd-field--var" }, [
              h("span", { class: "aimd-field__scope" }, "VAR"),
              h("span", { class: "aimd-field__name" }, refTarget),
            ]),
          ]),
        ])
      }

      // Edit mode: render as reference block with disabled input field inside
      if (!varItem) {
        // Fallback to simple tag if no item props
        return h("span", {
          "class": "aimd-ref aimd-ref--var",
          "data-aimd-type": "ref_var",
          "data-aimd-ref": refTarget,
        }, [
          h("span", { class: "aimd-ref__content" }, [
            h("span", { class: "aimd-field aimd-field--var" }, [
              h("span", { class: "aimd-field__scope" }, "VAR"),
              h("span", { class: "aimd-field__name" }, refTarget),
            ]),
          ]),
        ])
      }

      // Clone varItem and set disabled to true
      // Keep the original scope for model access, but mark it as a reference
      const refVarItem = {
        ...varItem,
        disabled: true,
        id: `ref-var-${varItem.scope}-${refTarget}`,
        // Add a flag to indicate this is a reference field
        isReference: true,
        // Keep the model reference so it shows the same value
      }

      // Render as reference block with AIMDItem component inside
      // Use a unique ID for the wrapper to avoid scroll conflicts
      return h("span", {
        "class": "aimd-ref aimd-ref--var",
        "data-aimd-type": "ref_var",
        "data-aimd-ref": refTarget,
        "data-aimd-scope": varItem.scope,
      }, [
        h("span", { class: "aimd-ref__content" }, [
          h("span", {
            class: "aimd-field-wrapper aimd-field-wrapper--inline aimd-field-wrapper--ref",
            id: `ref-var-${varItem.scope}-${refTarget}`,
          }, [h(AIMDItem, refVarItem)]),
        ]),
      ])
    },

    ref_fig: (node: AimdNode, _ctx: RenderContext) => {
      const refTarget = "refTarget" in node ? (node.refTarget as string) : node.id
      const figureNumber = "figureNumber" in node ? (node as any).figureNumber : undefined

      // Display figure number if available, otherwise show ID
      const displayText = figureNumber !== undefined ? `Figure ${figureNumber}` : `FIGURE ${refTarget}`

      // Render as link reference to the figure
      return h("a", {
        "class": "aimd-ref aimd-ref--fig",
        "data-aimd-type": "ref_fig",
        "data-aimd-ref": refTarget,
        "href": `#rf-${refTarget}`,
      }, [
        h("span", { class: "aimd-ref__content" }, displayText),
      ])
    },

    cite: (node: AimdNode, _ctx: RenderContext) => {
      const refs = "refs" in node ? (node.refs as string[]) : [node.id]

      return h("span", {
        "class": "aimd-cite",
        "data-aimd-type": "cite",
        "data-aimd-refs": refs.join(","),
      }, [
        h("span", { class: "aimd-cite__refs" }, `[${refs.join(", ")}]`),
      ])
    },

    fig: (node: AimdNode, _ctx: RenderContext) => {
      const figNode = node as any
      const figId = figNode.id || node.id
      const figSrc = figNode.src || ""
      const figTitle = figNode.title
      const figLegend = figNode.legend
      const figSequence = figNode.sequence

      return h(AimdFigure, {
        figId,
        figSrc,
        figTitle,
        figLegend,
        figSequence,
        resolveFile,
      })
    },
  } as unknown as Record<string, AimdComponentRenderer>
}
