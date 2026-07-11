import type { AimdNode } from "@airalogy/aimd-core/types"
import type { AimdRendererContext, VueRendererOptions } from "@airalogy/aimd-renderer"
import type { IAIMDItemProps } from "../types/aimd-types"
import { renderDefaultAimdNode } from "@airalogy/aimd-renderer"
import { h } from "vue"
import AIMDItem from "../components/aimd-item.vue"
import AIMDTag from "../components/aimd-tag.vue"
import CheckRenderer from "../components/check-renderer.vue"
import StepRenderer from "../components/step-renderer.vue"

type AimdRendererMap = NonNullable<VueRendererOptions["aimdRenderers"]>
export type AimdComponentRenderer = AimdRendererMap[string]

function getContextFieldValue(
  context: AimdRendererContext,
  item: Pick<IAIMDItemProps, "scope" | "prop">,
): unknown {
  const scopeValue = context.value?.[item.scope]
  if (!scopeValue || typeof scopeValue !== "object") {
    return undefined
  }

  const fieldValue = (scopeValue as Record<string, unknown>)[item.prop]
  if (!fieldValue || typeof fieldValue !== "object" || !("value" in fieldValue)) {
    return undefined
  }

  return (fieldValue as { value?: unknown }).value
}

function syncItemValue(item: IAIMDItemProps | null, context: AimdRendererContext): IAIMDItemProps | null {
  if (!item || !context.value) {
    return item
  }

  const externalValue = getContextFieldValue(context, item)
  if (externalValue === undefined || !item.model) {
    return item
  }

  return {
    ...item,
    model: {
      ...item.model,
      value: externalValue,
    },
  }
}

interface BaseNode {
  id: string
  scope: string
  type?: string
}

export function getPropsFromNode(node: BaseNode, variableList: IAIMDItemProps[]): IAIMDItemProps | null {
  const { id, scope, type } = node
  return variableList.find(
    item => item.scope === scope && item.prop === id && (!type || item.type === type),
  ) || null
}

export interface CreatePlatformAimdFormRenderersOptions {
  getTokenProps: (node: { id: string, scope: string, type?: string }) => IAIMDItemProps | null
}

/**
 * Platform-only adapters for its Naive UI record form controls.
 * Generic AIMD preview and fallback markup always comes from aimd-renderer.
 */
export function createPlatformAimdFormRenderers(
  options: CreatePlatformAimdFormRenderersOptions,
): Record<string, AimdComponentRenderer> {
  const { getTokenProps } = options

  return {
    var: (node: AimdNode, context: AimdRendererContext) => {
      const item = getTokenProps({ id: node.id, scope: "research_variable" })
      if (!item) {
        return renderDefaultAimdNode("var", node, context)
      }

      return h("span", {
        "class": "aimd-field-wrapper aimd-field-wrapper--inline",
        "id": `${node.scope}-${node.id}`,
        "data-has-variable": "true",
      }, [h(AIMDItem, syncItemValue(item, context)!)])
    },

    var_table: (node: AimdNode, context: AimdRendererContext) => {
      const columns = "columns" in node ? (node.columns as string[]) : []
      const item = getTokenProps({ id: node.id, scope: "research_variable" })
      if (!item) {
        return renderDefaultAimdNode("var_table", node, context)
      }

      const resolvedItem = columns.length > 0 && (!item.info?.subvars || item.info.subvars.length === 0)
        ? { ...item, info: { ...item.info, subvars: columns, name: node.id } }
        : item

      return h(AIMDTag, resolvedItem)
    },

    step: (node: AimdNode, context: AimdRendererContext) => {
      const step = "step" in node ? String(node.step) : "1"
      const hasCheck = "check" in node ? Boolean(node.check) : false
      const checkItem = hasCheck
        ? getTokenProps({ id: node.id, scope: "research_step", type: "rs-check" })
        : null
      const annotationItem = getTokenProps({ id: node.id, scope: "research_step", type: "rs-annotation" })

      return h(StepRenderer, {
        item: syncItemValue(checkItem, context),
        annotationItem: syncItemValue(annotationItem, context),
        name: node.id,
        step,
        check: hasCheck,
        content: [],
      })
    },

    check: (node: AimdNode, context: AimdRendererContext) => {
      const item = getTokenProps({ id: node.id, scope: "research_check" })
      const annotationItem = getTokenProps({ id: node.id, scope: "research_check", type: "rc-annotation" })

      return h(CheckRenderer, {
        item: syncItemValue(item, context),
        annotationItem: syncItemValue(annotationItem, context),
        name: node.id,
        content: [],
      })
    },

    ref_var: (node: AimdNode, context: AimdRendererContext) => {
      const refTarget = "refTarget" in node ? (node.refTarget as string) : node.id
      const item = getTokenProps({ id: refTarget, scope: "research_variable" })
      if (!item) {
        return renderDefaultAimdNode("ref_var", node, context)
      }

      const referenceItem = {
        ...item,
        disabled: true,
        id: `ref-var-${item.scope}-${refTarget}`,
        isReference: true,
      }

      return h("span", {
        "class": "aimd-ref aimd-ref--var",
        "data-aimd-type": "ref_var",
        "data-aimd-ref": refTarget,
        "data-aimd-scope": item.scope,
      }, [
        h("span", { class: "aimd-ref__content" }, [
          h("span", {
            class: "aimd-field-wrapper aimd-field-wrapper--inline aimd-field-wrapper--ref",
            id: `ref-var-${item.scope}-${refTarget}`,
          }, [h(AIMDItem, referenceItem)]),
        ]),
      ])
    },
  } as unknown as Record<string, AimdComponentRenderer>
}
