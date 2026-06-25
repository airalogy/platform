import type { Component, Ref } from "vue"
import type { ComboBoxItem, ComboBoxItemType, ComboBoxSubAction } from "./type"
import { type Editor, VueRenderer } from "@tiptap/vue-3"
import MentionList from "./mention-list.vue"

export interface ContextSubmenuItem {
  id: string
  title: string
  description: string
  icon?: Component
  metadata?: any
}
// export interface ContextProviderDescription {
//   title: string
//   displayTitle: string
//   description: string
//   renderInlineAs?: string
//   type: ContextProviderType
// }
function getSuggestion(
  items: (props: { query: string }) => Promise<ComboBoxItem[]>,
  enterSubmenu: (editor: Editor, providerId: string) => void = (editor) => { },
  onClose: () => void = () => { },
  onOpen: (component: VueRenderer) => void = () => { },
  onUpdate: (props: any) => void = () => { },
) {
  return {
    items,
    allowSpaces: true,
    render: () => {
      let component: VueRenderer

      const onExit = () => {
        component?.destroy()
        onClose()
      }

      return {
        onStart: (props: any) => {
          if (!props.clientRect) {
            console.log("no client rect")
            return
          }

          component = new VueRenderer(MentionList, {
            props: {
              ...props,
              enterSubmenu,
              onClose: onExit,
            },
            editor: props.editor,
          })

          onOpen(component)
        },

        onUpdate(props: any) {
          component.updateProps({ ...props, enterSubmenu })

          onUpdate(props)
        },

        onKeyDown(props: any) {
          if (props.event.key === "Escape") {
            onClose()

            return true
          }

          // FUCK: https://github.com/ueberdosis/tiptap/pull/5206
          return component.ref?.onKeyDown(props)
        },

        onExit,
      }
    },
  }
}

function getSubActionsForSubmenuItem(
  item: ContextSubmenuItem & { providerTitle: string },
): ComboBoxSubAction[] | undefined {
  if (item.providerTitle === "docs" && !item.metadata?.preIndexed) {
    return [
      {
        label: "Open in new tab",
        icon: "trash",
        action: () => {
          // TODO
        },
      },
    ]
  }

  return undefined
}

export function getContextProviderDropdownOptions(options: {
  availableContextProviders: Ref<(Chat.ContextProviderDescription)[]>
  getSubmenuContextItems:
  (
    providerTitle: string | undefined,
    query: string,
  ) => (ContextSubmenuItem & { providerTitle: string })[]

  enterSubmenu: (editor: Editor, providerId: string) => void
  onClose: () => void
  onOpen: (component: VueRenderer) => void
  onUpdate: (props: any) => void
  inSubmenu: Ref<string | undefined>
},
) {
  const { availableContextProviders, getSubmenuContextItems, enterSubmenu, onClose, onOpen, onUpdate, inSubmenu } = options

  const items = async ({ query }: { query: string }) => {
    if (inSubmenu.value) {
      const results = getSubmenuContextItems(
        inSubmenu.value,
        query,
      )
      return results.map((result) => {
        return {
          label: result.title,
          ...result,
          type: inSubmenu.value as ComboBoxItemType,
          query: result.id,
          subActions: getSubActionsForSubmenuItem(result),
        }
      })
    }

    const contextProviderMatches: any[]
      = availableContextProviders.value
        ?.filter(
          provider =>
            provider.title?.toLowerCase().startsWith(query.toLowerCase())
            || provider.displayTitle?.toLowerCase().startsWith(query.toLowerCase()),
        )
        .map(provider => ({
          name: provider.displayTitle,
          description: provider.description,
          id: provider.title,
          title: provider.displayTitle,
          label: provider.displayTitle,
          renderInlineAs: provider.renderInlineAs,
          type: "contextProvider" as ComboBoxItemType,
          contextProvider: provider,
        }))
        .sort((c, _) => (c.id === "file" ? -1 : 1)) || []

    if (contextProviderMatches.length === 0) {
      const results = getSubmenuContextItems(undefined, query)
      return results.map((result) => {
        return {
          ...result,
          label: result.title,
          type: result.providerTitle as ComboBoxItemType,
          query: result.id,
          icon: result.icon,
        }
      })
    }
    // else if (
    //   mainResults.length === availableContextProviders.value.length
    // ) {
    //   mainResults.push({
    //     title: "Add more context providers",
    //     type: "action",
    //     action: () => {
    //       // TODO
    //     },
    //     description: "",
    //   })
    // }
    return contextProviderMatches
  }

  return getSuggestion(items, enterSubmenu, onClose, onOpen, onUpdate)
}

export function getSlashCommandDropdownOptions(
  availableSlashCommands: Ref<ComboBoxItem[]>,
  onClose: () => void,
  onOpen: (component: VueRenderer) => void,
  parentSelector?: string,
) {
  const items = async ({ query }: { query: string }) => {
    // const options = [
    //   ...availableSlashCommands.value,
    //   {
    //     title: "Build a custom prompt",
    //     description: "Build a custom prompt",
    //     type: "action",
    //     id: "createPromptFile",
    //     label: "Create Prompt File",
    //     action: () => {
    //       // TODO
    //     },
    //     name: "Create Prompt File",
    //   },
    // ]
    return (
      availableSlashCommands.value.filter((slashCommand) => {
        if (!slashCommand.title) {
          return false
        }

        const sc = slashCommand.title?.substring(1).toLowerCase()
        const iv = query.toLowerCase()
        return sc.startsWith(iv)
      }) || []
    ).map(provider => ({
      name: provider.title,
      description: provider.description,
      id: provider.title,
      title: provider.title,
      label: provider.title,
      type: (provider.type ?? "slashCommand") as ComboBoxItemType,
      action: provider.action,
    }))
  }
  return getSuggestion(items, undefined, onClose, onOpen)
}
