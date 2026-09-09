import dagre from 'dagre'

const NODE_WIDTH = 170
const NODE_HEIGHT = 60

export function getLayoutedNodes(nodes, edges, direction = 'TB', dimensions = {}) {
  const defaultWidth = dimensions.width ?? NODE_WIDTH
  const defaultHeight = dimensions.height ?? NODE_HEIGHT
  const nodesep = dimensions.nodesep ?? 40
  const ranksep = dimensions.ranksep ?? 80

  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: direction, nodesep, ranksep })

  nodes.forEach((node) =>
    graph.setNode(node.id, {
      width: node.width ?? defaultWidth,
      height: node.height ?? defaultHeight,
    }),
  )
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))

  dagre.layout(graph)

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id)
    const width = node.width ?? defaultWidth
    const height = node.height ?? defaultHeight
    return {
      ...node,
      position: {
        x: x - width / 2,
        y: y - height / 2,
      },
    }
  })
}
