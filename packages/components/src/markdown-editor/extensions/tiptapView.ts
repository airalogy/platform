import type { Node as ProseMirrorNode } from "@tiptap/pm/model"
import type { Decoration, DecorationSource, NodeView as ProseMirrorNodeView } from "@tiptap/pm/view"
import type { Component, Ref } from "vue"
import { NodeView } from "@tiptap/core"
import { type DecorationWithType, type Editor, type NodeViewProps, type NodeViewRenderer, type NodeViewRendererProps, type VueNodeViewRendererOptions, VueRenderer } from "@tiptap/vue-3"

import { unrefElement } from "@vueuse/core"

class VueNodeView extends NodeView<Component, Editor, VueNodeViewRendererOptions> {
  renderer!: VueRenderer

  decorationClasses!: Ref<string>
  isMounted = false

  constructor(component: Component, props: NodeViewRendererProps, options?: Partial<VueNodeViewRendererOptions>) {
    super(component, props, options)
    this.mount()
  }

  mount() {
    if (this.isMounted) {
      return
    }

    const props = {
      editor: this.editor,
      node: this.node,
      decorations: this.decorations as DecorationWithType[],
      innerDecorations: this.innerDecorations,
      view: this.view,
      selected: false,
      extension: this.extension,
      HTMLAttributes: this.HTMLAttributes,
      getPos: () => this.getPos(),
      updateAttributes: (attributes = {}) => this.updateAttributes(attributes),
      deleteNode: () => this.deleteNode(),
    } satisfies NodeViewProps

    const onDragStart = this.onDragStart.bind(this)

    this.decorationClasses = ref(this.getDecorationClasses())

    const extendedComponent = defineComponent({
      extends: { ...this.component },
      props: Object.keys(props),
      template: (this.component as any).template,
      setup: (reactiveProps, { expose }) => {
        provide("onDragStart", onDragStart)
        provide("decorationClasses", this.decorationClasses)

        // Create an object to store the exposed refs
        let exposedRefs: Record<string, any> | undefined

        // Call the original setup function with a proper expose function
        const setupResult = (this.component as any).setup?.(reactiveProps, {
          expose: (exposed: Record<string, any>) => {
            // Store the exposed refs
            exposedRefs = exposed
          },
        })

        // Expose the collected refs from the original component
        if (exposedRefs) {
          expose(exposedRefs)
        }

        return setupResult
      },
      // add support for scoped styles
      // @ts-expect-error assign to any
      __scopeId: this.component.__scopeId,
      // add support for CSS Modules
      // @ts-expect-error assign to any
      __cssModules: this.component.__cssModules,
      // add support for vue devtools
      // @ts-expect-error assign to any
      __name: this.component.__name,
      // @ts-expect-error assign to any
      __file: this.component.__file,
    })

    this.handleSelectionUpdate = this.handleSelectionUpdate.bind(this)
    this.editor.on("selectionUpdate", this.handleSelectionUpdate)

    this.renderer = new VueRenderer(extendedComponent, {
      editor: this.editor,
      props,
    })

    this.isMounted = true
  }

  /**
   * Return the DOM element.
   * This is the element that will be used to display the node view.
   */
  get dom() {
    if (!this.renderer.element || !this.renderer.element.hasAttribute("data-node-view-wrapper")) {
      throw new Error("Please use the NodeViewWrapper component for your node view.")
    }

    return this.renderer.element as HTMLElement
  }

  /**
   * Return the content DOM element.
   * This is the element that will be used to display the rich-text content of the node.
   */
  get contentDOM() {
    if (this.node.isLeaf) {
      return null
    }

    const { contentDOM } = this.renderer.ref

    return unrefElement(contentDOM)
  }

  /**
   * On editor selection update, check if the node is selected.
   * If it is, call `selectNode`, otherwise call `deselectNode`.
   */
  handleSelectionUpdate() {
    const { from, to } = this.editor.state.selection
    const pos = this.getPos()

    if (typeof pos !== "number") {
      return
    }

    if (from <= pos && to >= pos + this.node.nodeSize) {
      if (this.renderer.props.selected) {
        return
      }

      this.selectNode()
    }
    else {
      if (!this.renderer.props.selected) {
        return
      }

      this.deselectNode()
    }
  }

  /**
   * On update, update the React component.
   * To prevent unnecessary updates, the `update` option can be used.
   */
  update(
    node: ProseMirrorNode,
    decorations: readonly Decoration[],
    innerDecorations: DecorationSource,
  ): boolean {
    const rerenderComponent = (props?: Record<string, any>) => {
      this.decorationClasses.value = this.getDecorationClasses()
      this.renderer.updateProps(props)
    }

    if (typeof this.options.update === "function") {
      const oldNode = this.node
      const oldDecorations = this.decorations
      const oldInnerDecorations = this.innerDecorations

      this.node = node
      this.decorations = decorations
      this.innerDecorations = innerDecorations

      return this.options.update({
        oldNode,
        oldDecorations,
        newNode: node,
        newDecorations: decorations,
        oldInnerDecorations,
        innerDecorations,
        updateProps: () => rerenderComponent({ node, decorations, innerDecorations }),
      })
    }

    if (node.type !== this.node.type) {
      return false
    }

    if (node === this.node && this.decorations === decorations && this.innerDecorations === innerDecorations) {
      return true
    }

    this.node = node
    this.decorations = decorations
    this.innerDecorations = innerDecorations

    rerenderComponent({ node, decorations, innerDecorations })

    return true
  }

  /**
   * Select the node.
   * Add the `selected` prop and the `ProseMirror-selectednode` class.
   */
  selectNode() {
    this.renderer.updateProps({
      selected: true,
    })
    if (this.renderer.element) {
      this.renderer.element.classList.add("ProseMirror-selectednode")
    }
  }

  /**
   * Deselect the node.
   * Remove the `selected` prop and the `ProseMirror-selectednode` class.
   */
  deselectNode() {
    this.renderer.updateProps({
      selected: false,
    })
    if (this.renderer.element) {
      this.renderer.element.classList.remove("ProseMirror-selectednode")
    }
  }

  getDecorationClasses() {
    return (
      this.decorations
        // @ts-expect-error attrs is not typed
        .map(item => item.type.attrs.class)
        .flat()
        .join(" ")
    )
  }

  destroy() {
    this.renderer.destroy()
    this.editor.off("selectionUpdate", this.handleSelectionUpdate)
  }
}

export function VueNodeViewRenderer(
  component: Component<NodeViewProps>,
  options?: Partial<VueNodeViewRendererOptions>,
): NodeViewRenderer {
  return (props) => {
    // try to get the parent component
    // this is important for vue devtools to show the component hierarchy correctly
    // maybe it's `undefined` because <editor-content> isn't rendered yet
    if (!(props.editor as Editor).contentComponent) {
      return {} as unknown as ProseMirrorNodeView
    }
    // check for class-component and normalize if neccessary
    const normalizedComponent = typeof component === "function" && "__vccOpts" in component
      ? (component.__vccOpts as Component)
      : component

    return new VueNodeView(normalizedComponent, props, options)
  }
}
