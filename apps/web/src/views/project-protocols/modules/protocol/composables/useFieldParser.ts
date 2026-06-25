import type { AimdTableLink, AimdTemplateEnv, AimdVarTableField, FieldKey, IDynamicTableNode, IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { FiledName } from "@airalogy/shared/utils"
import type { ComputedRef, MaybeRef, Ref } from "vue"
import type { FieldRecord } from "../helpers/parseFieldStructure"
import type { IFieldItem } from "../types/types"
import { getSubvarNames } from "@airalogy/aimd-core"
import { fieldEventKey, getFinalIndent } from "@airalogy/aimd-renderer"
import { getRefValue, scopeKeyRecord } from "@airalogy/shared/utils"
import { useEventBus } from "@vueuse/core"
import { difference as _difference, union as _union } from "lodash-es"

type TableNode = IDynamicTableNode | AimdVarTableField

interface ITableEvent {
  source: TableNode
  args: any[]
}

type TemplateRecord = NonNullable<AimdTemplateEnv["record"]>
type TemplateRefs = NonNullable<AimdTemplateEnv["refs"]>
interface TemplateRefItem {
  id: string
  line: number
  sequence: number
}

function getTableNodeName(node: TableNode): string {
  if ("name" in node && typeof node.name === "string") {
    return node.name
  }

  if ("id" in node && typeof node.id === "string") {
    return node.id
  }

  return ""
}

function getTableNodeLink(node: TableNode): AimdTableLink | null {
  const link = node.link
  if (!link || typeof link !== "object") {
    return null
  }

  if ("target" in link && "source" in link) {
    return link as AimdTableLink
  }

  return null
}

function getLegacyLinkTargetName(node: TableNode): string | undefined {
  const link = node.link
  if (!link || typeof link !== "object" || !("node" in link)) {
    return undefined
  }

  const target = link.node
  if (target && typeof target === "object" && "name" in target && typeof target.name === "string") {
    return target.name
  }

  return undefined
}

function getReferenceName(ref: TemplateRefItem): string {
  return ref.id
}

export function useFieldParser(
  fieldModel: FieldRecord,
  protocol: MaybeRef<ProtocolModels.ProtocolInfo | null | undefined>,
  scopeList: ComputedRef<ScopeFieldKey[]>,
  fieldPropList: Ref<(string | [string, string[]])[][]>,
  refRecord: Ref<Record<"ref_step" | "rv_ref", Record<string, any>>>,
  tableRecord: Ref<Record<string, Record<string, Record<"title" | "type" | "description" | "pattern", string> & { sequence: number, link?: any }>>>,
  tableEmitterRecord: Ref<Record<"master" | "slave", Record<string, ((...args: any[]) => void)[]>>>,
  minimal = false,
) {
  const fieldEventBus = minimal ? null : useEventBus<string>(fieldEventKey)

  function parseFormFields(
    fields: Partial<Record<FiledName, any[]>>,
    typed?: Record<string, Record<string, any>>,
  ) {
    const currScopeList = scopeList.value
    const { fields: protocolFields } = unref(protocol) || {}

    if (!Array.isArray(currScopeList) || currScopeList.length === 0) {
      return
    }

    const sortedFieldList = currScopeList.map((scope) => {
      const propList = protocolFields?.[scope as FieldKey]
      if (!propList) {
        return []
      }

      const protocolPropList = propList.map(({ name }) => name)
      const fieldKey = scopeKeyRecord[scope] as FiledName
      const targetFieldPropList = fields?.[fieldKey] || []
      if (targetFieldPropList.length === 0) {
        return protocolPropList
      }
      const diff = _difference(targetFieldPropList, protocolPropList)
      if (diff.length === 0) {
        return protocolPropList
      }

      return _union(protocolPropList, diff)
    })

    sortedFieldList.forEach((fieldProps, idx) => {
      const scope = currScopeList[idx]
      const targetFields = (fieldModel[scope] || {}) as any
      const targetInputType = typed?.[scope]?.input_type

      if (!fieldModel[scope]) {
        fieldModel[scope] = targetFields
      }

      const rawFieldRecord = unref(protocol)?.fields?.[scope as FieldKey]

      fieldProps.forEach((prop) => {
        const targetField = rawFieldRecord?.find(({ name }) => name === prop)

        if (Array.isArray(prop)) {
          const [groupName, groupProps] = prop as unknown as [string, string[]]
          const children = groupProps.map((it) => {
            const item: IFieldItem = {
              label: it,
              title: it,
              scope,
              disabled: false,
              required: false,
              type: targetInputType?.[it] ?? "textarea",
              group: groupName,
              children: [],
              id: `group-${groupName}-${it}`,
            }

            return item
          })

          const prevChildren = targetFields[groupName]?.children
          if (!Array.isArray(prevChildren)) {
            targetFields[groupName] = {
              label: groupName,
              title: groupName,
              scope,
              disabled: false,
              required: false,
              type: targetInputType?.[groupName] ?? "textarea",
              group: groupName,
              children,
              id: `group-${groupName}`,
            }
          }
        }
        else if (targetFields[prop]) {
          if (targetField && !targetFields[prop].raw) {
            targetFields[prop].raw = targetField

            if (targetField.type) {
              targetFields[prop].type = targetField.type
            }
          }
        }
        else {
          targetFields[prop] = {
            label: prop,
            title: prop,
            scope,
            disabled: false,
            required: false,
            type: targetField?.type ?? targetInputType?.[prop] ?? "textarea",
            value: undefined,
            raw: targetField,
            id: `field-${prop}`,
          }
        }
      })
    })

    if (fieldModel.research_workflow) {
      const targetIndex = currScopeList.indexOf("research_workflow")
      sortedFieldList[targetIndex] = Object.keys(fieldModel.research_workflow).filter(
        it => it !== "__SCOPE__",
      )
    }

    fieldPropList.value = sortedFieldList
  }

  function parseRefs(
    record: TemplateRecord,
    refs: TemplateRefs,
  ) {
    const { ref_step, ref_var } = refs
    const stepRecord = ((record as Record<string, unknown>).byName ?? record.byId ?? {}) as Record<string, any>
    if (ref_step) {
      ref_step.forEach((ref) => {
        const refName = getReferenceName(ref)
        const target = stepRecord[refName]

        if (target) {
          const sequence = typeof target.sequence === "number" ? target.sequence : -1
          const name = typeof target.name === "string" ? target.name : refName
          const level = typeof target.level === "number" ? target.level : -1
          const suffix = typeof target.suffix === "string" ? target.suffix : ""

          const refTarget = refRecord.value.ref_step[name]

          if (refTarget) {
            refTarget.level = level
            refTarget.sequence = sequence
            refTarget.indent = `Step ${getFinalIndent(target)}`
            refTarget.suffix = suffix

            if (Array.isArray(refTarget.dependent)) {
              ; (refTarget.dependent as TemplateRefItem[]).push(ref)
            }
            else {
              refTarget.dependent = [ref]
            }
          }
          else {
            refRecord.value.ref_step[name] = {
              level,
              sequence,
              indent: `Step ${getFinalIndent(target)}`,
              suffix,
              dependent: [ref],
            }
          }
        }
        else {
          refRecord.value.ref_step[refName] = {
            level: -1,
            sequence: -1,
            indent: `Step ${refName}`,
            suffix: "NOT FOUND",
            dependent: [ref],
          }
        }
      })
    }

    if (ref_var) {
      ref_var.forEach((ref) => {
        const name = getReferenceName(ref)
        const refTarget = refRecord.value.rv_ref[name]

        if (refTarget) {
          if (Array.isArray(refTarget.dependent)) {
            ; (refTarget.dependent as TemplateRefItem[]).push(ref)
          }
          else {
            refTarget.dependent = [ref]
          }
        }
        else {
          refRecord.value.rv_ref[name] = { name, dependent: [ref] }
        }
      })
    }
  }

  function parseVarTable(
    tables: [string, TableNode][] | Record<string, TableNode>,
    record?: FieldRecord,
  ) {
    const entries = Array.isArray(tables) ? tables : Object.entries(tables)
    const { json_schema, assigners } = unref(protocol) || {}
    const variableRecord = record || fieldModel.research_variable

    if (!variableRecord) {
      return
    }

    const { research_variable: schema } = json_schema || {}
    const { properties, $defs } = schema || {}

    entries.forEach(([groupKey, node]) => {
      const link = getTableNodeLink(node)
      if (link && fieldEventBus) {
        const nodeName = getTableNodeName(node)
        const master = tableEmitterRecord.value.master[nodeName]
        const slave = tableEmitterRecord.value.slave[groupKey]

        const masterEmitter = (...args: any[]) =>
          fieldEventBus.emit("update-table-master", { source: node, args } as ITableEvent)
        if (Array.isArray(slave)) {
          slave.push(masterEmitter)
        }
        else {
          tableEmitterRecord.value.slave[groupKey] = [masterEmitter]
        }

        const slaveEmitter = (...args: any[]) =>
          fieldEventBus.emit("update-table-slave", { source: node, args } as ITableEvent)
        if (Array.isArray(master)) {
          master.push(slaveEmitter)
        }
        else {
          let targetName: string | undefined
          if (link.target?.name) {
            targetName = link.target.name
          }
          else {
            targetName = getLegacyLinkTargetName(node)
          }
          if (targetName) {
            tableEmitterRecord.value.master[targetName] = [slaveEmitter]
          }
        }
      }

      const targetGroup = variableRecord?.[groupKey as keyof typeof variableRecord]
      const targetGroupProperties = properties?.[groupKey]

      // Get subvars from multiple sources and normalize to string[]
      // Uses getSubvarNames to handle both string[] and {name: string}[] formats
      const rawSubvars = (node as any).subvars || targetGroup?.raw?.subvars || []
      // Also get subvarDefs if available (contains pattern info from markdown parsing)
      const subvarDefs = (node as any).subvarDefs || targetGroup?.raw?.subvarDefs || {}
      const subvarNames = getSubvarNames(rawSubvars)

      if (subvarNames.length === 0) {
        return
      }

      // Ensure fieldModel.research_variable[groupKey] exists with subvars in raw
      if (targetGroup && targetGroup.raw && !targetGroup.raw.subvars) {
        targetGroup.raw.subvars = rawSubvars // Keep original format for metadata
      }

      const { dependentRecord } = targetGroup || {}

      // Try to get schema-defined properties for subvars
      let groupProperties: Record<string, any> = {}
      if (targetGroupProperties?.items?.$ref && $defs) {
        const refPath = targetGroupProperties.items.$ref
        const targetGroupItem = getRefValue(schema, refPath)
        if (targetGroupItem?.properties) {
          groupProperties = targetGroupItem.properties
        }
      }

      const prefix = `${groupKey}.`

      subvarNames.forEach((itemName, idx) => {
        // Get subvar metadata from rawSubvars if available
        const subvarMeta = Array.isArray(rawSubvars)
          ? rawSubvars.find((s: any) => (typeof s === "string" ? s : s.name) === itemName)
          : null
        const subvarInfo = typeof subvarMeta === "object" ? subvarMeta : null
        // Also check subvarDefs for pattern (from markdown parsing in parseFieldStructure)
        const subvarDefInfo = subvarDefs?.[itemName]

        // Get target from schema or create from subvar metadata
        const schemaTarget = groupProperties[itemName]

        // Extract pattern from subvar metadata or subvarDefs
        // IMPORTANT: subvarDefInfo comes from markdown parsing and should have correct escaping
        // Prioritize subvarDefInfo over subvarInfo as it has properly parsed pattern
        const pattern = subvarDefInfo?.pattern || subvarDefInfo?.kwargs?.pattern || subvarInfo?.pattern || subvarInfo?.kwargs?.pattern || schemaTarget?.pattern

        const target = (schemaTarget || {
          title: subvarInfo?.title || itemName,
          type: subvarInfo?.type || "string",
          description: subvarInfo?.description || "",
        }) as Record<"title" | "type" | "description" | "pattern", string> & { assigner?: ProtocolModels.Assigner, dependent?: { name: string, scope: IRecordDataKey }[], default?: unknown }

        // Add pattern if it exists
        if (pattern) {
          target.pattern = pattern
        }

        // Add default value from subvar metadata if available
        if (subvarInfo?.default !== undefined) {
          target.default = subvarInfo.default
        }

        const targetAssigner = assigners?.[`${prefix}${itemName}`]
        const targetDependent = dependentRecord?.[`${prefix}${itemName}`]
        if (targetAssigner) {
          target.assigner = targetAssigner
        }
        if (targetDependent) {
          target.dependent = targetDependent
        }

        if (tableRecord.value[groupKey]) {
          tableRecord.value[groupKey][itemName] = { ...target, sequence: idx } as any
        }
        else {
          tableRecord.value[groupKey] = { [itemName]: target as any }
        }
      })
    })
  }

  function handleParseField(data: AimdTemplateEnv) {
    const { fields, typed, record, tables, refs } = data

    if (!fields || !record || !tables || !refs) {
      return
    }

    /** parse form */
    parseFormFields(fields, typed)

    /** parse ref_step */
    parseRefs(record, refs)

    /** parse var_table */
    parseVarTable(tables)
  }

  return {
    handleParseField,
    parseFormFields,
    parseRefs,
    parseVarTable,
  }
}
