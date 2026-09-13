import './CompanyList.css'
import { IconEdit } from '@tabler/icons-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'

function CompanyList({ onEditCompany }) {
  const companies = useAppStore((state) => state.companies)
  const activeCompanyId = useAppStore((state) => state.activeCompanyId)
  const setActiveCompanyId = useAppStore((state) => state.setActiveCompanyId)
  const navigate = useNavigate()
  const location = useLocation()

  // Switching companies should land on whatever tab the user was already
  // looking at (e.g. Financial > Expenses stays Financial > Expenses for
  // the newly selected company) instead of always resetting to
  // Management > Roadmap — only fall back to that default when the current
  // page isn't inside a company workspace at all (e.g. Dashboard, Settings).
  const buildTargetPath = (companyId) => {
    const segments = location.pathname.split('/').filter(Boolean)
    const companyIndex = segments.indexOf('company')
    if (companyIndex === -1 || segments.length <= companyIndex + 1) {
      return `/company/${companyId}/management/roadmap`
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
          <div key={company.id} className={`company-list__item ${isActive ? 'is-active' : ''}`}>
            <span
              className="company-list__accent"
              style={{
                background: `linear-gradient(180deg, ${company.accentFrom}, ${company.accentTo})`,
              }}
            />
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
