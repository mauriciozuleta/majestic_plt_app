import './UserRow.css'
import { IconChevronDown, IconUserCircle } from '@tabler/icons-react'

function UserRow() {
  return (
    <button type="button" className="user-row">
      <span className="user-row__avatar">
        <IconUserCircle size={16} stroke={1.8} />
      </span>
      <span className="user-row__name">M. Zuleta</span>
      <span className="user-row__chevron">
        <IconChevronDown size={14} stroke={1.8} />
      </span>
    </button>
  )
}

export default UserRow
