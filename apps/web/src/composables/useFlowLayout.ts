import dagre from "@dagrejs/dagre"
// import type { Node as DagreNode } from "@dagrejs/dagre"
import { type Edge, type Node, Position, useVueFlow } from "@vue-flow/core"

/**
 * Composable to run the layout algorithm on the graph.
 * It uses the `dagre` library to calculate the layout of the nodes and edges.
 */
export function useFlowLayout(flowId?: string, multigraph = true) {
  const { findNode } = useVueFlow(flowId)

  const graph = ref(new dagre.graphlib.Graph())

  const previousDirection = ref<"LR" | "TB">("LR")

  function layout<T = unknown>(nodes: Node[], edges: Edge<T>[], direction: "LR" | "TB") {
    // we create a new graph instance, in case some nodes/edges were removed, otherwise dagre would act as if they were still there
    const dagreGraph = new dagre.graphlib.Graph({ multigraph })

    graph.value = dagreGraph

    dagreGraph.setDefaultEdgeLabel(() => ({}))

    const isHorizontal = direction === "LR"
    dagreGraph.setGraph({
      rankdir: direction,
      nodesep: 20,
      ranksep: 30,
      edgesep: 10,
      marginx: 10,
      marginy: 10,
    })

    previousDirection.value = direction

    nodes.forEach(({ id }) => {
      // if you need width+height of nodes for your layout, you can use the dimensions property of the internal node (`GraphNode` type)
      const graphNode = findNode(id)

      dagreGraph.setNode(id, {
        width: graphNode?.dimensions.width || 150,
        height: graphNode?.dimensions.height || 50,
      })
    })

    edges.forEach((edge) => {
      const { data, source, target } = edge
      // if (data) {
      //   const {} = data
      // }
      dagreGraph.setEdge(edge.source, edge.target)
    })

    dagre.layout(dagreGraph)

    // 创建一个 y 坐标到节点的映射
    const yGroupMap: Record<number, any[]> = {}

    // 遍历所有节点，按 y 坐标进行分组
    dagreGraph.nodes().forEach((v) => {
      const node = dagreGraph.node(v)
      const y = node.y

      if (!yGroupMap[y]) {
        yGroupMap[y] = []
      }
      yGroupMap[y].push(node)
    })

    // 调整每组中的节点，使中心点在同一 y 坐标
    Object.values(yGroupMap).forEach((group) => {
      const baseY = group[0].y + group[0].height / 2

      group.forEach((node, idx) => {
        if (idx === 0) {
          return
        }
        node.y = baseY - node.height / 2
      })
    })

    // set nodes with updated positions
    return nodes.map((node) => {
      const { id, targetPosition, sourcePosition } = node

      const nodeWithPosition = dagreGraph.node(id)

      // dagre returns center coordinates, but VueFlow expects top-left coordinates
      // so we need to subtract half of the node's width and height
      return {
        ...node,
        data: { ...node.data, raw: nodeWithPosition },
        rank: nodeWithPosition.rank,
        targetPosition: targetPosition || (isHorizontal ? Position.Left : Position.Top),
        sourcePosition: sourcePosition || (isHorizontal ? Position.Right : Position.Bottom),
        position: {
          x: nodeWithPosition.x - nodeWithPosition.width / 2,
          y: nodeWithPosition.y - nodeWithPosition.height / 2,
        },
      }
    })
  }

  const getNodePosition = (id: string) => {
    const node = graph.value.node(id)

    return { x: node.x - node.width / 2, y: node.y - node.height / 2 }
  }

  return { graph, layout, previousDirection, getNodePosition }
}
