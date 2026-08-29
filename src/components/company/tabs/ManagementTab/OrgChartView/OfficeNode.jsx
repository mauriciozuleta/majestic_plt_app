import { Handle, Position } from '@xyflow/react'
import './OfficeNode.css'

function OfficeNode({ data, selected }) {
  return (
    <div className={`office-node ${selected ? 'is-selected' : ''}`}>
      <Handle type="target" position={Position.Top} className="office-node__handle" />
      <div className="office-node__title">{data.officeName}</div>
      <div className={`office-node__employee ${!data.employeeName ? 'is-vacant' : ''}`}>
        {data.employeeName || 'Vacant'}
      </div>
      {data.area ? <div className="office-node__area">{data.area}</div> : null}
      <Handle type="source" position={Position.Bottom} className="office-node__handle" />
    </div>
  )
}

export default OfficeNode
