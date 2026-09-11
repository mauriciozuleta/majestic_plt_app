import './Sidebar.css'
import {
  IconChartDots,
  IconHome,
  IconLayoutDashboard,
  IconSettings,
  IconPlus,
  IconWorld,
} from '@tabler/icons-react'
import SidebarNavItem from './SidebarNavItem'
import CompanyList from './CompanyList'
import UserRow from '../../user/UserRow'
import Chatbox from '../../chatbox/Chatbox'
import AddCompanyModal from '../../company/AddCompanyModal/AddCompanyModal'
import { useAppStore } from '../../../store/useAppStore'
import { addCompany as createCompany, updateCompany as updateCompanyApi } from '../../../services/companies'
import { useState } from 'react'

function Sidebar() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCompany, setEditingCompany] = useState(null)
  const addCompany = useAppStore((state) => state.addCompany)
  const updateCompanyInStore = useAppStore((state) => state.updateCompany)

  const handleAddCompany = async (payload) => {
    const newCompany = await createCompany({
      ...payload,
      accentFrom: payload.accentFrom || '#35D399',
      accentTo: payload.accentTo || '#0EA5E9',
    })

    addCompany(newCompany)
  }

  const handleUpdateCompany = async (payload) => {
    const updated = await updateCompanyApi(editingCompany.id, {
      ...payload,
      accentFrom: payload.accentFrom || editingCompany.accentFrom,
      accentTo: payload.accentTo || editingCompany.accentTo,
    })

    updateCompanyInStore(updated)
  }

  const closeCompanyModal = () => {
    setIsModalOpen(false)
    setEditingCompany(null)
  }

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-shell__inner">
        <SidebarNavItem icon={IconHome} label="Home" to="/" />
        <SidebarNavItem icon={IconLayoutDashboard} label="Control dashboard" to="/dashboard" />
        <SidebarNavItem icon={IconWorld} label="Commercial Structure" to="/commercial-structure" />
        <SidebarNavItem icon={IconChartDots} label="Simulations" to="/simulations" />

        <div className="sidebar-shell__divider" />

        <button type="button" className="sidebar-shell__add-company" onClick={() => setIsModalOpen(true)}>
          <span className="sidebar-shell__add-company-icon">
            <IconPlus size={14} stroke={2} />
          </span>
          <span>Add company</span>
        </button>

        <div className="sidebar-shell__company-list-label">Companies</div>
        <CompanyList onEditCompany={setEditingCompany} />

        <div className="sidebar-shell__spacer" />

        <div className="sidebar-shell__divider" />

        <SidebarNavItem icon={IconSettings} label="Settings" to="/settings" />
        <UserRow />
        <Chatbox />
      </div>

      <AddCompanyModal
        isOpen={isModalOpen || !!editingCompany}
        initialCompany={editingCompany}
        onClose={closeCompanyModal}
        onSave={editingCompany ? handleUpdateCompany : handleAddCompany}
      />
    </aside>
  )
}

export default Sidebar
