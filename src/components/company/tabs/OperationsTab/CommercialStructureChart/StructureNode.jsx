import { Handle, Position } from '@xyflow/react'
import { IconTrash } from '@tabler/icons-react'
import './StructureNode.css'

function StructureNode({ data, selected }) {
  const canDelete = (data.kind === 'country' || data.kind === 'branch') && typeof data.onDelete === 'function'

  return (
    <div className={`structure-node is-${data.kind} ${selected ? 'is-selected' : ''}`}>
      <Handle type="target" position={Position.Top} className="structure-node__handle" />
      {canDelete && (
        <button
          type="button"
          className="structure-node__delete"
          title={`Delete this ${data.kind}`}
          onClick={(event) => {
            event.stopPropagation()
            data.onDelete()
          }}
        >
          <IconTrash size={13} stroke={1.8} />
        </button>
      )}
      <div className="structure-node__kind">{data.kind}</div>
      <div className="structure-node__title" title={data.label}>
        {data.label}
      </div>
      {data.sub ? (
        <div className="structure-node__sub" title={data.sub}>
          {data.sub}
        </div>
      ) : null}
      {data.kind !== 'company' && (
        <div className={`structure-node__manager ${!data.manager ? 'is-vacant' : ''}`} title={data.manager || undefined}>
          {data.manager || 'No manager set'}
        </div>
      )}
      {data.user ? (
        <div className="structure-node__user" title={data.user}>
          {data.user}
        </div>
      ) : null}
      <Handle type="source" position={Position.Bottom} className="structure-node__handle" />
    </div>
  )
}

export default StructureNode
