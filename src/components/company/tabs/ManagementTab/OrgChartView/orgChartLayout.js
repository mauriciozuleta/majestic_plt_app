import dagre from 'dagre'

const NODE_WIDTH = 170
const NODE_HEIGHT = 60

export function getLayoutedNodes(nodes, edges, direction = 'TB') {
  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: direction, nodesep: 40, ranksep: 80 })

  nodes.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))

  dagre.layout(graph)

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id)
    return {
      ...node,
      position: {
        x: x - NODE_WIDTH / 2,
        y: y - NODE_HEIGHT / 2,
      },
    }
  })
}
