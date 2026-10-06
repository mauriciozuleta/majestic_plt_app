import './Sidebar.css'
import {
  IconChartDots,
  IconDatabase,
  IconFiles,
  IconHome,
  IconLayoutDashboard,
  IconMapSearch,
  IconSettings,
  IconShip,
  IconSitemap,
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
        {/* A scrollable section: four tabs show, the rest scroll. */}
        <div className="sidebar-shell__nav">
          <SidebarNavItem icon={IconHome} label="Home" to="/" />
          <SidebarNavItem icon={IconSitemap} label="Corporate structure" to="/corporate-structure" />
          <SidebarNavItem icon={IconLayoutDashboard} label="Control dashboard" to="/dashboard" />
          <SidebarNavItem icon={IconWorld} label="Commercial Structure" to="/commercial-structure" />
          <SidebarNavItem icon={IconMapSearch} label="Market Analysis" to="/market-analysis" />
          <SidebarNavItem icon={IconShip} label="Global Trade Data" to="/global-trade-data" />
          <SidebarNavItem icon={IconChartDots} label="Simulations" to="/simulations" />
          <SidebarNavItem icon={IconFiles} label="Documentation" to="/documentation" />
        </div>

        <div className="sidebar-shell__divider" />

        <button type="button" className="sidebar-shell__add-company" onClick={() => setIsModalOpen(true)}>
          <span className="sidebar-shell__add-company-icon">
            <IconPlus size={14} stroke={2} />
          </span>
          <span>Add company</span>
        </button>

        <div className="sidebar-shell__company-list-label">Companies</div>
        <div className="sidebar-shell__companies">
          <CompanyList onEditCompany={setEditingCompany} />
        </div>

        <div className="sidebar-shell__bottom">
          <div className="sidebar-shell__divider" />

          <SidebarNavItem icon={IconDatabase} label="RAG Files" to="/rag-files" />
          <SidebarNavItem icon={IconSettings} label="Settings" to="/settings" />
          <UserRow />
          <Chatbox />
        </div>
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
