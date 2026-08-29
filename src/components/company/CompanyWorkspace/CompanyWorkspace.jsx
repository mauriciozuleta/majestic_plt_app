import { useEffect } from 'react'
import './CompanyWorkspace.css'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

const tabConfig = {
  operations: {
    label: 'Operations',
    subTabs: [],
  },
  management: {
    label: 'Management',
    subTabs: ['roadmap', 'org-chart', 'payroll', 'settings'],
  },
  financial: {
    label: 'Financial',
    subTabs: ['revenue', 'cost-of-sales', 'expenses', 'reports'],
  },
  simulator: {
    label: 'Simulator',
    subTabs: [],
  },
  drivers: {
    label: 'Drivers',
    subTabs: [],
  },
  documentation: {
    label: 'Documentation',
    subTabs: [],
  },
}

function CompanyWorkspace() {
  const { companyId } = useParams()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const company = useAppStore((state) =>
    state.companies.find((item) => item.id === companyId || slugify(item.name) === companyId),
  )
  const removeCompany = useAppStore((state) => state.removeCompany)

  useEffect(() => {
    if (!company || company.id === companyId) return

    const suffix = pathname.split('/').slice(3).join('/')
    navigate(`/company/${company.id}${suffix ? `/${suffix}` : ''}`, { replace: true })
  }, [company, companyId, navigate, pathname])

  if (!company) return null

  const activeTab = (() => {
    const segments = pathname.split('/').filter(Boolean)
    const companyIndex = segments.indexOf(companyId)
    const topLevelSegment = segments[companyIndex + 1]
    return topLevelSegment && tabConfig[topLevelSegment] ? topLevelSegment : 'management'
  })()

  const accentStyle = {
    background: `linear-gradient(90deg, ${company.accentFrom}22, ${company.accentTo}22)`,
  }

  return (
    <section className="company-workspace">
      <div className="company-workspace__header" style={accentStyle}>
        <div className="company-workspace__identity">
          <span
            className="company-workspace__logo"
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
            {!company.logo && company.name.slice(0, 2).toUpperCase()}
          </span>
          <span className="company-workspace__name">{company.name}</span>
        </div>

        <nav className="company-workspace__tabs" aria-label="Company tabs">
          {Object.entries(tabConfig).map(([key, config]) => (
            <NavLink
              key={key}
              to={
                key === 'operations'
                  ? `/company/${companyId}/operations`
                  : key === 'management'
                    ? `/company/${companyId}/management/roadmap`
                    : key === 'financial'
                      ? `/company/${companyId}/financial/revenue`
                      : key === 'simulator'
                        ? `/company/${companyId}/simulator`
                        : key === 'drivers'
                          ? `/company/${companyId}/drivers`
                          : `/company/${companyId}/documentation`
              }
              className={({ isActive }) =>
                `company-workspace__tab ${isActive || activeTab === key ? 'is-active' : ''} ${
                  key === 'operations' ? 'company-workspace__tab--operations' : ''
                }`
              }
            >
              {config.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="company-workspace__subtabs">
        {activeTab === 'management' || activeTab === 'financial' ? (
          tabConfig[activeTab].subTabs.map((entry) => (
            <NavLink
              key={entry}
              to={`/company/${companyId}/${activeTab}/${entry}`}
              className={({ isActive }) => `company-workspace__subtab ${isActive ? 'is-active' : ''}`}
            >
              {entry.replace(/-/g, ' ')}
            </NavLink>
          ))
        ) : null}
      </div>

      <div className="company-workspace__content">
        <Outlet />
      </div>
    </section>
  )
}

export default CompanyWorkspace
