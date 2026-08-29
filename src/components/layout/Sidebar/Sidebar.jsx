import './Sidebar.css'
import {
  IconChartDots,
  IconHome,
  IconLayoutDashboard,
  IconSettings,
  IconPlus,
} from '@tabler/icons-react'
import SidebarNavItem from './SidebarNavItem'
import CompanyList from './CompanyList'
import UserRow from '../../user/UserRow'
import Chatbox from '../../chatbox/Chatbox'
import AddCompanyModal from '../../company/AddCompanyModal/AddCompanyModal'
import { useAppStore } from '../../../store/useAppStore'
import { addCompany as createCompany } from '../../../services/companies'
import { useState } from 'react'

function Sidebar() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const addCompany = useAppStore((state) => state.addCompany)

  const handleAddCompany = async (payload) => {
    const newCompany = await createCompany({
      ...payload,
      accentFrom: payload.accentFrom || '#35D399',
      accentTo: payload.accentTo || '#0EA5E9',
    })

    addCompany(newCompany)
  }

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-shell__inner">
        <SidebarNavItem icon={IconHome} label="Home" to="/" />
        <SidebarNavItem icon={IconLayoutDashboard} label="Control dashboard" to="/dashboard" />
        <SidebarNavItem icon={IconChartDots} label="Simulations" to="/simulations" />

        <div className="sidebar-shell__divider" />

        <button type="button" className="sidebar-shell__add-company" onClick={() => setIsModalOpen(true)}>
          <span className="sidebar-shell__add-company-icon">
            <IconPlus size={14} stroke={2} />
          </span>
          <span>Add company</span>
        </button>

        <div className="sidebar-shell__company-list-label">Companies</div>
        <CompanyList />

        <div className="sidebar-shell__spacer" />

        <div className="sidebar-shell__divider" />

        <SidebarNavItem icon={IconSettings} label="Settings" to="/settings" />
        <UserRow />
        <Chatbox />
      </div>

      <AddCompanyModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSave={handleAddCompany} />
    </aside>
  )
}

export default Sidebar
