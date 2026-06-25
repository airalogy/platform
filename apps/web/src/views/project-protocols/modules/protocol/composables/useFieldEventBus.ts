import type { IDynamicTableNode, IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { AssignerNode } from "../components/AssignerProgressModal.vue"
import type { IFieldChangePayload } from "../types/types"
import type { IHandleAssignerPayload, IHandleDependentPayload } from "./useAssignerManagement"
import { fieldEventKey } from "@/utils/template/eventKey"
import { useClosableMessage } from "@airalogy/composables"
import { useDebounceFn, useEventBus } from "@vueuse/core"
import Big from "big.js"
import { get, set } from "lodash-es"
import { nanoid } from "nanoid"
import { nextTick, type Ref, toRaw } from "vue"
import { getAssignerProgress } from "./useAssignerProgress"

interface IFieldBatchPayload {
  list: {
    scope: IRecordDataKey
    prop: string
    value?: any
    info: any
    assigner: ProtocolModels.Assigner
    dependent: {
      scope: IRecordDataKey
      name: string
    }[]
  }[]
  batchId: string
}

interface IQueuedFieldChange {
  scope: IRecordDataKey
  prop: string
  value?: any
  info?: any
  assigner?: ProtocolModels.Assigner
  dependent?: { scope: IRecordDataKey, name: string }[]
}

interface IOperationPayload {
  action: {
    operation: "update"
    rf_name: string
    rf_value: any
  }
  resolve: (value?: any) => void
  reject: (reason?: any) => void
}

function getAssignerAssignedFields(assigner: ProtocolModels.Assigner | undefined, fallbackField: string): string[] {
  if (Array.isArray(assigner?.assigned_fields) && assigner.assigned_fields.length > 0) {
    return assigner.assigned_fields
  }

  return [fallbackField]
}

export function useFieldEventBus(
  fieldModel: any,
  expandedNamesRef: Ref<string[]>,
  handleAssigner: (payload: IHandleAssignerPayload) => Promise<string | boolean>,
  handleDependent: (payload: IHandleDependentPayload) => void,
  handleAssignerCancel: (payload: Pick<IHandleAssignerPayload, "prop" | "info">) => void,
  updateField: (model: any, payload: IFieldChangePayload) => Promise<void>,
  emit: { (e: "update:field", payload: { scope: IRecordDataKey, prop: string, value: any, info?: any }): void },
  varScopeRecord?: Ref<Record<string, string>>,
  assigners?: Record<string, ProtocolModels.Assigner>,
) {
  const fieldEventBus = useEventBus<string>(fieldEventKey)
  const message = useClosableMessage()

  // Queue management for field changes
  const changeQueue: IQueuedFieldChange[] = []
  let isProcessingQueue = false

  /**
   * Get unique key for a field change
   */
  function getFieldChangeKey(change: IQueuedFieldChange): string {
    const { scope, prop, info } = change
    const groupKey = info?.group ? `:${info.group}:${info.row}` : ""
    return `${scope}:${prop}${groupKey}`
  }

  /**
   * Add a field change to the queue, merging with existing changes for same field
   */
  function enqueueFieldChange(change: IQueuedFieldChange) {
    const key = getFieldChangeKey(change)
    // Find and remove any existing change for the same field
    const existingIndex = changeQueue.findIndex(c => getFieldChangeKey(c) === key)
    if (existingIndex !== -1) {
      changeQueue.splice(existingIndex, 1)
    }
    changeQueue.push(change)
  }

  function isTableSubfieldDependency(depName: string, group?: string): boolean {
    return Boolean(group) && depName.startsWith(`${group}.`)
  }

  function resolveDependentChange(
    dep: { scope: IRecordDataKey, name: string },
    info?: Record<string, any>,
  ) {
    const group = info?.group as string | undefined
    const row = info?.row as number | undefined

    if (isTableSubfieldDependency(dep.name, group) && typeof row === "number") {
      const targetRow = get(fieldModel as any, ["research_variable", group, "value", row] as any) as any
      const varName = dep.name.slice(group!.length + 1)

      return {
        assigner: get(fieldModel as any, [dep.scope, group, "assignerRecord", dep.name] as any) as ProtocolModels.Assigner | undefined,
        value: get(targetRow, [varName, "value"]),
        info,
        dependent: (get(fieldModel as any, [dep.scope, group, "dependentRecord", dep.name] as any) || []) as { scope: IRecordDataKey, name: string }[],
      }
    }

    return {
      assigner: assigners?.[dep.name] || get(fieldModel as any, [dep.scope, dep.name, "assigner"]) as ProtocolModels.Assigner | undefined,
      value: get(fieldModel as any, [dep.scope, dep.name, "value"]),
      info: undefined,
      dependent: (get(fieldModel as any, [dep.scope, dep.name, "dependent"]) || []) as { scope: IRecordDataKey, name: string }[],
    }
  }

  function getManualAssignerDependents(scope: IRecordDataKey, prop: string, info?: Record<string, any>) {
    const group = info?.group as string | undefined

    if (!group) {
      return get(fieldModel, [scope, prop, "dependent"])
    }

    return [
      ...(get(fieldModel, ["research_variable", group, "dependentRecord", `${group}.${prop}`]) || []),
      ...(get(fieldModel, ["research_variable", group, "dependentRecord", prop]) || []),
      ...(get(fieldModel, ["research_variable", group, "dependent"]) || []),
    ]
  }

  function isAssignerSuccess(result: string | boolean): result is true {
    return result === true
  }

  function getAssignerFailureMessage(result: string | boolean) {
    return typeof result === "string" && result.trim()
      ? result
      : "Assignment failed"
  }

  /**
   * Process the queued field changes with assigner execution
   */
  async function processChangeQueue() {
    if (isProcessingQueue || changeQueue.length === 0) {
      return
    }

    isProcessingQueue = true
    const progress = getAssignerProgress()

    try {
      // Take all changes from the queue
      const currentBatch = changeQueue.splice(0)
      const batchId = nanoid()

      // First, apply field value updates immediately
      for (const change of currentBatch) {
        await updateField(fieldModel, change as IFieldChangePayload)
      }

      // Collect all dependent assigners that need to be triggered
      const dependentAssigners: IFieldBatchPayload["list"] = []

      for (const change of currentBatch) {
        const { info, dependent } = change

        if (!dependent || dependent.length === 0)
          continue

        // Collect all dependent assigners
        for (const dep of dependent) {
          const depScope = dep.scope
          const depName = dep.name
          const resolved = resolveDependentChange(dep, info)
          const assigner = resolved.assigner

          if (!assigner)
            continue

          // Skip manual mode assigners
          if (assigner.mode === "manual")
            continue

          // Skip auto_first if already assigned
          if (assigner.mode === "auto_first") {
            const assignedSetPath = resolved.info?.group
              ? [depScope, resolved.info.group, "assignedSet"]
              : [depScope, depName, "assignedSet"]
            const assignedSet = get(fieldModel, assignedSetPath)
            if (assignedSet?.has(depName))
              continue
          }

          const depValue = resolved.value

          // Avoid duplicates
          const exists = dependentAssigners.some(
            d => d.prop === depName && d.info?.group === resolved.info?.group && d.info?.row === resolved.info?.row,
          )
          if (!exists) {
            dependentAssigners.push({
              scope: depScope,
              prop: depName,
              value: depValue,
              info: resolved.info,
              assigner,
              dependent: resolved.dependent,
            })
          }
        }
      }

      // If there are dependent assigners, build execution plan and execute
      if (dependentAssigners.length > 0) {
        const { levelGroups: executionPlan, progressNodes } = buildAssignerExecutionPlan(dependentAssigners)
        const maxLevel = Math.max(...Array.from(executionPlan.keys()), -1)

        if (progressNodes.length > 0) {
          if (progress.state.visible) {
            // Add to existing progress if already showing
            progress.addNodes(progressNodes)
          }
          else {
            // Start fresh progress display
            progress.show("Assigning fields...")
            progress.setNodes(progressNodes)
          }
        }

        // Execute assigners level by level
        for (let level = 0; level <= maxLevel; level++) {
          const levelItems = executionPlan.get(level) || []
          if (levelItems.length === 0)
            continue

          progress.setCurrentLevel(level)
          console.log(`[Assigner Queue] 🚀 Executing level ${level}: [${levelItems.map(i => i.prop).join(", ")}]`)

          // Mark level items as running
          levelItems.forEach(({ prop }) => {
            progress.updateNodeStatus(prop, "running")
          })

          // Execute all assigners in this level in parallel
          const levelPromises = levelItems.map(async ({ scope, prop, assigner, info }) => {
            try {
              const result = await handleAssigner({
                scope,
                prop,
                assigner,
                fieldModel,
                info,
                batchId,
                from: "dependent",
                skipCascade: true,
              })
              progress.updateNodeStatus(
                prop,
                isAssignerSuccess(result) ? "completed" : "error",
                isAssignerSuccess(result) ? undefined : getAssignerFailureMessage(result),
              )
              return result
            }
            catch (e) {
              progress.updateNodeStatus(prop, "error", (e as Error).message)
              throw e
            }
          })

          await Promise.allSettled(levelPromises)
          console.log(`[Assigner Queue] ✅ Level ${level} completed`)
        }
      }

      // Emit field-update-complete for each change
      for (const change of currentBatch) {
        fieldEventBus.emit("field-update-complete", change)
      }
    }
    finally {
      isProcessingQueue = false

      // If new changes were added during processing, process them
      if (changeQueue.length > 0) {
        // Use nextTick to allow the UI to update
        await nextTick()
        processChangeQueue()
      }
    }
  }

  /**
   * Debounced queue processor (300ms delay to batch rapid changes)
   */
  const debouncedProcessQueue = useDebounceFn(() => {
    processChangeQueue()
  }, 300)

  /**
   * Build dependency graph and compute topological levels for assigners
   * Returns assigners grouped by execution level and progress nodes for visualization
   */
  function buildAssignerExecutionPlan(
    list: IFieldBatchPayload["list"],
  ): { levelGroups: Map<number, typeof list>, progressNodes: AssignerNode[] } {
    // Step 0: Build maps for dependency checking
    // Map of field -> item (for checking if field has value)
    const fieldValueMap = new Map<string, typeof list[0]>()
    list.forEach((item) => {
      fieldValueMap.set(item.prop, item)
    })

    // Map of field -> assigner that produces it (including manual assigners)
    const fieldToProducerAssigner = new Map<string, typeof list[0]>()
    list.forEach((item) => {
      if (item.assigner) {
        const assignedFields = getAssignerAssignedFields(item.assigner, item.prop)
        assignedFields.forEach((field: string) => {
          fieldToProducerAssigner.set(field, item)
        })
      }
    })

    // Helper: Check if a field depends on an unexecuted manual assigner (direct or indirect)
    const skippedFields = new Set<string>()

    function shouldSkipAssigner(item: typeof list[0], visited: Set<string> = new Set()): boolean {
      if (skippedFields.has(item.prop)) {
        return true
      }
      if (visited.has(item.prop)) {
        return false // Avoid infinite loop
      }
      visited.add(item.prop)

      const depFields = item.assigner?.dependent_fields || []
      for (const depField of depFields) {
        const producer = fieldToProducerAssigner.get(depField)
        if (!producer?.assigner) {
          continue
        }

        // Case 1: Direct dependency on manual assigner without value
        if (producer.assigner.mode === "manual") {
          const fieldItem = fieldValueMap.get(depField)
          const hasValue = fieldItem?.value !== undefined && fieldItem?.value !== null
          if (!hasValue) {
            return true
          }
        }

        // Case 2: Dependency on another assigner that will be skipped
        if (producer.assigner.mode !== "manual" && shouldSkipAssigner(producer, visited)) {
          return true
        }
      }

      // Case 3: Check if any dependency is a plain input field without value
      for (const depField of depFields) {
        const producer = fieldToProducerAssigner.get(depField)
        // If depField is not produced by any assigner, it's an input field
        if (!producer) {
          // First check if the field is in our batch list
          const fieldItem = fieldValueMap.get(depField)
          let hasValue = fieldItem?.value !== undefined && fieldItem?.value !== null

          // If not in batch list, check directly from fieldModel
          // This handles the case where we're only processing dependent assigners
          // and the input field they depend on is not part of the current batch
          if (!fieldItem && varScopeRecord) {
            const targetScope = varScopeRecord.value?.[depField] as IRecordDataKey
            if (targetScope) {
              const fieldValue = get(fieldModel, [targetScope, depField, "value"])
              hasValue = fieldValue !== undefined && fieldValue !== null && fieldValue !== ""
            }
          }

          if (!hasValue) {
            return true // Skip: depends on input field without value
          }
        }
      }

      return false
    }

    // Step 1: Build a map of field -> assigner that assigns it (excluding manual)
    // Also filter out assigners that depend on unexecuted manual assigners (directly or indirectly)
    const fieldToAssigner = new Map<string, typeof list[0]>()

    // First pass: identify all assigners that should be skipped
    list.forEach((item) => {
      if (!item.assigner || item.assigner.mode === "manual") {
        return
      }
      if (shouldSkipAssigner(item)) {
        skippedFields.add(item.prop)
        console.log(`[Assigner Plan] Skipping ${item.prop}: depends on unexecuted manual assigner`)
      }
    })

    // Second pass: filter out skipped assigners
    const assignerItems = list.filter((item) => {
      if (!item.assigner || item.assigner.mode === "manual") {
        return false
      }
      return !skippedFields.has(item.prop)
    })

    assignerItems.forEach((item) => {
      // Use assigned_fields if available, otherwise use item.prop as fallback
      // This handles cases where assigned_fields might be undefined or empty
      const assignedFields = getAssignerAssignedFields(item.assigner, item.prop)
      assignedFields.forEach((field: string) => {
        fieldToAssigner.set(field, item)
      })
    })

    // Step 2: Compute level for each assigner using topological sort
    // Level = max(levels of all assigners that assign to my dependent_fields) + 1
    const assignerLevels = new Map<string, number>()

    function computeLevel(item: typeof list[0], visited: Set<string>): number {
      const key = item.prop
      if (assignerLevels.has(key)) {
        return assignerLevels.get(key)!
      }

      // Detect cycle
      if (visited.has(key)) {
        console.warn(`[Assigner] Circular dependency detected for ${key}`)
        return 0
      }
      visited.add(key)

      let maxDepLevel = -1
      const depFields = item.assigner?.dependent_fields || []

      for (const depField of depFields) {
        const depAssigner = fieldToAssigner.get(depField)
        if (depAssigner) {
          const depLevel = computeLevel(depAssigner, visited)
          maxDepLevel = Math.max(maxDepLevel, depLevel)
        }
      }

      const level = maxDepLevel + 1
      assignerLevels.set(key, level)
      return level
    }

    // Compute levels for all assigners
    assignerItems.forEach((item) => {
      computeLevel(item, new Set())
    })

    // Step 3: Group assigners by level
    const levelGroups = new Map<number, typeof list>()
    assignerItems.forEach((item) => {
      const level = assignerLevels.get(item.prop) ?? 0
      if (!levelGroups.has(level)) {
        levelGroups.set(level, [])
      }
      levelGroups.get(level)!.push(item)
    })

    // Step 4: Build progress nodes for visualization
    const progressNodes: AssignerNode[] = assignerItems.map(item => ({
      prop: item.prop,
      level: assignerLevels.get(item.prop) ?? 0,
      dependsOn: item.assigner?.dependent_fields || [],
      assignedFields: getAssignerAssignedFields(item.assigner, item.prop),
      status: "pending" as const,
    }))

    // Log execution plan
    const maxLevel = Math.max(...Array.from(levelGroups.keys()), -1)
    console.log(`[Assigner Plan] Execution plan with ${maxLevel + 1} levels:`)
    for (let level = 0; level <= maxLevel; level++) {
      const items = levelGroups.get(level) || []
      console.log(`  Level ${level}: [${items.map(i => i.prop).join(", ")}]`)
    }

    return { levelGroups, progressNodes }
  }

  function setupFieldEventHandlers() {
    // Handle batch field changes
    fieldEventBus.on(async (event, payload: IFieldBatchPayload) => {
      if (event !== "preview-field-change-batch")
        return

      const { list, batchId } = payload
      if (!Array.isArray(list) || list.length === 0) {
        return
      }

      // Step 1: Set values for non-assigner fields first
      list.forEach(({ scope, prop, value, assigner, info }) => {
        if (scope === "research_workflow")
          return

        const controlledValue = typeof value === "undefined" ? null : value
        let path = scope === "var_table"
          ? `research_variable.${scope}.value[${info!.row}].${prop}`
          : `${scope}.${prop}.value`

        if (scope === "research_step" || scope === "research_check") {
          if (typeof value === "boolean")
            path = `${path}.checked`
          if (typeof value === "string")
            path = `${path}.annotation`
        }

        if (!assigner || assigner.mode === "manual") {
          set(fieldModel, path, controlledValue)
          emit("update:field", {
            scope,
            info,
            prop: scope === "var_table" ? info!.group : prop,
            value: scope === "var_table"
              ? get(fieldModel, `research_variable.${info!.group}.value`)
              : controlledValue,
          })
        }
      })

      // Step 2: Build execution plan (topological sort by levels)
      const { levelGroups: executionPlan, progressNodes } = buildAssignerExecutionPlan(list)
      const maxLevel = Math.max(...Array.from(executionPlan.keys()), -1)

      // Step 3: Show progress modal if there are assigners to execute
      const progress = getAssignerProgress()
      if (progressNodes.length > 0) {
        progress.show("Assigning fields...")
        progress.setNodes(progressNodes)
      }

      // Step 4: Execute assigners level by level
      // Wait for all assigners in current level to complete before starting next level
      for (let level = 0; level <= maxLevel; level++) {
        const levelItems = executionPlan.get(level) || []
        if (levelItems.length === 0)
          continue

        progress.setCurrentLevel(level)
        console.log(`[Assigner Plan] 🚀 Executing level ${level}: [${levelItems.map(i => i.prop).join(", ")}]`)

        // Mark level items as running
        levelItems.forEach(({ prop }) => {
          progress.updateNodeStatus(prop, "running")
        })

        // Execute all assigners in this level in parallel
        // skipCascade: true because we're using planned execution, not cascade triggering
        const levelPromises = levelItems.map(async ({ scope, prop, assigner, info }) => {
          try {
            const result = await handleAssigner({ scope, prop, assigner, fieldModel, info, batchId, from: "assigner", skipCascade: true })
            progress.updateNodeStatus(
              prop,
              isAssignerSuccess(result) ? "completed" : "error",
              isAssignerSuccess(result) ? undefined : getAssignerFailureMessage(result),
            )
            return result
          }
          catch (e) {
            progress.updateNodeStatus(prop, "error", (e as Error).message)
            throw e
          }
        })

        // Wait for all assigners in this level to complete
        await Promise.allSettled(levelPromises)
        console.log(`[Assigner Plan] ✅ Level ${level} completed`)
      }

      // Progress modal will auto-close after all completed (handled by component)

      // Step 4: Emit field-update-complete for each field in the batch
      list.forEach((item) => {
        fieldEventBus.emit("field-update-complete", {
          scope: item.scope,
          prop: item.prop,
          value: item.value,
          info: item.info,
          assigner: item.assigner,
          dependent: item.dependent,
          batchId,
        })
      })
    })

    // Handle single field changes and focus
    fieldEventBus.on(async (event, payload: IFieldChangePayload & {
      batchId?: string
      assigner?: ProtocolModels.Assigner
      dependent?: { scope: IRecordDataKey, name: string }[]
    }) => {
      if (event === "preview-field-focus" || event === "field-tag-focus") {
        const { scope } = payload
        const isExpand = expandedNamesRef.value.findIndex(it => it === scope) !== -1
        if (!isExpand) {
          expandedNamesRef.value.push(scope)
          void nextTick(() => fieldEventBus.emit(event, payload))
        }
      }

      if (event === "preview-field-change") {
        // Add change to queue for batched processing with debounce
        enqueueFieldChange({
          scope: payload.scope,
          prop: payload.prop,
          value: payload.value,
          info: payload.info,
          assigner: payload.assigner,
          dependent: payload.dependent,
        })
        debouncedProcessQueue()
        return
      }

      if (event === "assigner-request") {
        const { scope, prop, assigner, info } = payload
        if (assigner) {
          const progress = getAssignerProgress()
          const batchId = nanoid()

          // For manual assigner triggered by button click:
          // 1. First execute the triggered assigner
          // 2. After it completes, collect and execute downstream dependents
          // This ensures downstream dependents see the updated value

          // Create progress node for the triggered assigner
          const triggeredNode: AssignerNode = {
            prop,
            level: 0,
            dependsOn: assigner.dependent_fields || [],
            assignedFields: getAssignerAssignedFields(assigner, prop),
            status: "pending",
          }

          // Show progress with just the triggered assigner first
          progress.show("Assigning fields...")
          progress.setNodes([triggeredNode])

          // Level 0: Execute the triggered assigner
          progress.setCurrentLevel(0)
          console.log(`[Assigner Request] 🚀 Executing triggered assigner: ${prop}`)
          progress.updateNodeStatus(prop, "running")

          let triggeredSuccess = false
          try {
            const result = await handleAssigner({
              scope,
              prop,
              assigner,
              fieldModel,
              info,
              batchId,
              from: "assigner",
              skipCascade: true,
            })
            triggeredSuccess = isAssignerSuccess(result)
            progress.updateNodeStatus(
              prop,
              triggeredSuccess ? "completed" : "error",
              triggeredSuccess ? undefined : getAssignerFailureMessage(result),
            )
          }
          catch (e) {
            progress.updateNodeStatus(prop, "error", (e as Error).message)
          }

          // Only proceed with downstream dependents if the triggered assigner succeeded
          if (triggeredSuccess) {
            // Now collect downstream dependent assigners (non-manual only)
            // At this point, the triggered assigner's value is already in fieldModel
            const dependentList: IFieldBatchPayload["list"] = []
            const processedDeps = new Set<string>()

            const collectDependents = (depList: { scope: IRecordDataKey, name: string }[] | undefined, parentInfo: any) => {
              if (!depList || depList.length === 0)
                return

              for (const dep of depList) {
                const resolved = resolveDependentChange(dep, parentInfo)
                const depKey = `${dep.scope}:${dep.name}:${resolved.info?.group || ""}:${resolved.info?.row || ""}`
                if (processedDeps.has(depKey))
                  continue
                processedDeps.add(depKey)

                const depAssigner = resolved.assigner
                if (!depAssigner || depAssigner.mode === "manual")
                  continue

                dependentList.push({
                  scope: dep.scope,
                  prop: dep.name,
                  value: resolved.value,
                  info: resolved.info,
                  assigner: depAssigner,
                  dependent: resolved.dependent,
                })

                // Recursively collect further dependents
                collectDependents(resolved.dependent, resolved.info)
              }
            }

            // Collect all downstream dependents
            const deps = getManualAssignerDependents(scope, prop, info)
            collectDependents(deps, info)

            if (dependentList.length > 0) {
              // Build execution plan for downstream dependents
              const { levelGroups: dependentExecutionPlan, progressNodes: dependentProgressNodes } = buildAssignerExecutionPlan(dependentList)

              // Adjust levels: downstream dependents start from level 1
              dependentProgressNodes.forEach((node) => {
                node.level += 1
              })

              // Update progress nodes to include downstream dependents
              const allProgressNodes = [triggeredNode, ...dependentProgressNodes]
              progress.setNodes(allProgressNodes)

              const maxLevel = Math.max(0, ...dependentProgressNodes.map(n => n.level))

              // Execute downstream dependents level by level (starting from level 1)
              for (let level = 0; level <= maxLevel - 1; level++) {
                const levelItems = dependentExecutionPlan.get(level) || []
                if (levelItems.length === 0)
                  continue

                progress.setCurrentLevel(level + 1)
                console.log(`[Assigner Request] 🚀 Executing level ${level + 1}: [${levelItems.map(i => i.prop).join(", ")}]`)

                levelItems.forEach(({ prop: p }) => {
                  progress.updateNodeStatus(p, "running")
                })

                const levelPromises = levelItems.map(async ({ scope: s, prop: p, assigner: a, info: i }) => {
                  try {
                    const result = await handleAssigner({
                      scope: s,
                      prop: p,
                      assigner: a,
                      fieldModel,
                      info: i,
                      batchId,
                      from: "assigner",
                      skipCascade: true,
                    })
                    progress.updateNodeStatus(
                      p,
                      isAssignerSuccess(result) ? "completed" : "error",
                      isAssignerSuccess(result) ? undefined : getAssignerFailureMessage(result),
                    )
                    return result
                  }
                  catch (e) {
                    progress.updateNodeStatus(p, "error", (e as Error).message)
                    throw e
                  }
                })

                await Promise.allSettled(levelPromises)
                console.log(`[Assigner Request] ✅ Level ${level + 1} completed`)
              }
            }
          }
        }
        return
      }

      if (event === "assigner-cancel") {
        const { prop, info } = payload
        handleAssignerCancel({ prop, info })

        return
      }
      if (event === "assigner-cancel-batch") {
        const { dependent } = payload
        if (Array.isArray(dependent)) {
          dependent.forEach(({ name }) => {
            handleAssignerCancel({ prop: name })
          })
        }

        return
      }

      if (event === "update-table-slave") {
        const { source, args } = payload as unknown as {
          source: IDynamicTableNode
          args: any[]
        }

        const emitPayload = args[0]
        if (emitPayload.type === "add-row")
          fieldEventBus.emit("add-slave-table-row", { source, payload: emitPayload.payload })

        if (emitPayload.type === "remove-row")
          fieldEventBus.emit("remove-slave-table-row", { source, payload: emitPayload.payload })
      }
    })

    // Handle operation field updates
    fieldEventBus.on(async (event, payload: IOperationPayload) => {
      if (event !== "operation-form-field-update")
        return

      const {
        action: { rf_name, rf_value },
        reject,
        resolve,
      } = payload

      // Use rf_name directly as prop, don't remove the rv_ prefix
      const prop = rf_name
      const target = fieldModel.research_variable[prop]

      if (!target) {
        reject({
          success: false,
          rf_name,
          error_code: "not_found",
          message: `The ${rf_name} is not found.`,
        })
        return
      }

      if (target.assigner && target.assigner.mode !== "manual") {
        reject({
          success: false,
          rf_name,
          error_code: "not_assignable",
          message: `The ${rf_name} is not assignable.`,
        })
        return
      }

      const controlledValue = target.type === "number" || target.type === "integer" || target.type === "float"
        ? new Big(rf_value)
        : String(rf_value)

      const { value: _, ...targetRest } = toRaw(target)

      const emitPayload: IFieldChangePayload = {
        prop,
        ...targetRest,
        value: Number.isNaN(Number(rf_value))
          ? rf_value
          : {
              displayedValue: controlledValue.toString(),
              type: "number",
              value: controlledValue,
            },
        scope: "research_variable",
      }

      fieldEventBus.emit("form-field-change", emitPayload)
      fieldEventBus.emit("preview-field-scroll", emitPayload)

      await updateField(fieldModel, emitPayload)

      resolve({
        success: true,
        rf_name,
        rf_value_updated: rf_value,
        message: `The value of ${rf_name} has been set to ${rf_value}.`,
      })

      message.success(`The value of ${rf_name} has been set to ${rf_value}.`)
    })
  }

  return {
    fieldEventBus,
    setupFieldEventHandlers,
  }
}
