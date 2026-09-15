import { Handle, Position } from '@xyflow/react'
import './CompanyNode.css'

function CompanyNode({ data }) {
  const initials = data.name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

  const isSubsidiary = data.dependency === 'Children'

  return (
    <div className="company-node">
      <Handle type="target" position={Position.Top} className="company-node__handle" />
      <span
        className="company-node__logo"
        style={
          data.logo
            ? {
                backgroundImage: `url(${data.logo})`,
                backgroundSize: 'contain',
                backgroundPosition: 'center',
                backgroundRepeat: 'no-repeat',
                backgroundColor: 'var(--bg-card)',
              }
            : { background: `linear-gradient(135deg, ${data.accentFrom}, ${data.accentTo})` }
        }
      >
        {!data.logo && initials}
      </span>
      <span className="company-node__name">{data.name}</span>
      <span className={`company-node__badge ${isSubsidiary ? 'is-subsidiary' : 'is-standalone'}`}>
        {isSubsidiary ? 'Subsidiary' : 'Stand-alone'}
      </span>
      {isSubsidiary && data.parentName ? <span className="company-node__parent">of {data.parentName}</span> : null}
      <Handle type="source" position={Position.Bottom} className="company-node__handle" />
    </div>
  )
}

export default CompanyNode
