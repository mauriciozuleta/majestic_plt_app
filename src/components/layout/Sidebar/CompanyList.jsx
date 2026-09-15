import './CompanyList.css'
import { useState } from 'react'
import { IconEdit, IconGripVertical } from '@tabler/icons-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'
import { getLastCompanyPath } from '../../../utils/lastCompanyPath'

function CompanyList({ onEditCompany }) {
  const companies = useAppStore((state) => state.companies)
  const activeCompanyId = useAppStore((state) => state.activeCompanyId)
  const setActiveCompanyId = useAppStore((state) => state.setActiveCompanyId)
  const reorderCompanies = useAppStore((state) => state.reorderCompanies)
  const navigate = useNavigate()
  const location = useLocation()
  // Only the grab handle can start a drag — the row itself stays a plain
  // click target. armedCompanyId is set on the handle's mousedown (before
  // the browser's own drag gesture begins) and is what the item's own
  // `draggable` attribute reads, so grabbing anywhere else on the row (the
  // name, the edit icon) never triggers a drag.
  const [armedCompanyId, setArmedCompanyId] = useState(null)
  const [dragOverCompanyId, setDragOverCompanyId] = useState(null)

  const handleDragStart = (event, companyId) => {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', companyId)
  }

  const handleDragOver = (event, companyId) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
    if (dragOverCompanyId !== companyId) setDragOverCompanyId(companyId)
  }

  const handleDrop = (event, targetCompanyId) => {
    event.preventDefault()
    const draggedCompanyId = event.dataTransfer.getData('text/plain')
    setDragOverCompanyId(null)
    if (draggedCompanyId && draggedCompanyId !== targetCompanyId) {
      reorderCompanies(draggedCompanyId, targetCompanyId)
    }
  }

  const handleDragEnd = () => {
    setArmedCompanyId(null)
    setDragOverCompanyId(null)
  }

  // Switching companies should land on whatever tab the user was already
  // looking at (e.g. Financial > Expenses stays Financial > Expenses for
  // the newly selected company) instead of always resetting to
  // Management > Roadmap — only fall back to that default when the current
  // page isn't inside a company workspace at all (e.g. Dashboard, Settings).
  const buildTargetPath = (companyId) => {
    const segments = location.pathname.split('/').filter(Boolean)
    const companyIndex = segments.indexOf('company')
    if (companyIndex === -1 || segments.length <= companyIndex + 1) {
      // Not currently inside any company's workspace (e.g. coming from
      // Home or Settings) — land back on this company's own last-visited
      // tab rather than always resetting to Management ▸ Roadmap.
      const lastPath = getLastCompanyPath(companyId)
      return `/company/${companyId}${lastPath ? `/${lastPath}` : '/management/roadmap'}`
    }
    const rest = segments.slice(companyIndex + 2)
    return `/company/${companyId}${rest.length ? `/${rest.join('/')}` : '/management/roadmap'}`
  }

  return (
    <div className="company-list">
      {companies.map((company) => {
        const isActive = company.id === activeCompanyId
        const initials = company.name
          .split(' ')
          .slice(0, 2)
          .map((part) => part[0])
          .join('')
          .toUpperCase()

        return (
          <div
            key={company.id}
            className={`company-list__item ${isActive ? 'is-active' : ''} ${dragOverCompanyId === company.id ? 'is-drag-over' : ''}`}
            draggable={armedCompanyId === company.id}
            onDragStart={(event) => handleDragStart(event, company.id)}
            onDragOver={(event) => handleDragOver(event, company.id)}
            onDrop={(event) => handleDrop(event, company.id)}
            onDragEnd={handleDragEnd}
          >
            <span
              className="company-list__accent"
              style={{
                background: `linear-gradient(180deg, ${company.accentFrom}, ${company.accentTo})`,
              }}
            />
            <button
              type="button"
              className="company-list__grab"
              onMouseDown={() => setArmedCompanyId(company.id)}
              aria-label={`Drag to reorder ${company.name}`}
              title="Drag to reorder"
            >
              <IconGripVertical size={14} stroke={1.8} />
            </button>
            <button
              type="button"
              className="company-list__row"
              onClick={() => {
                setActiveCompanyId(company.id)
                navigate(buildTargetPath(company.id))
              }}
            >
              <span
                className="company-list__logo"
                style={
                  company.logo
                    ? {
                        backgroundImage: `url(${company.logo})`,
                        backgroundSize: 'contain',
                        backgroundPosition: 'center',
                        backgroundRepeat: 'no-repeat',
                        backgroundColor: 'var(--bg-card)',
                      }
                    : {
                        background: `linear-gradient(135deg, ${company.accentFrom}, ${company.accentTo})`,
                      }
                }
              >
                {!company.logo && initials}
              </span>
              <span className="company-list__name">{company.name}</span>
            </button>
            <button
              type="button"
              className="company-list__edit"
              onClick={(event) => {
                event.stopPropagation()
                onEditCompany?.(company)
              }}
              aria-label={`Edit ${company.name}`}
              title="Edit company"
            >
              <IconEdit size={14} stroke={1.8} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

export default CompanyList
