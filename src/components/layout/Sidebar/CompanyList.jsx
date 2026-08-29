import './CompanyList.css'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'

function CompanyList() {
  const companies = useAppStore((state) => state.companies)
  const activeCompanyId = useAppStore((state) => state.activeCompanyId)
  const setActiveCompanyId = useAppStore((state) => state.setActiveCompanyId)
  const navigate = useNavigate()

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
          <button
            type="button"
            key={company.id}
            className={`company-list__item ${isActive ? 'is-active' : ''}`}
            onClick={() => {
              setActiveCompanyId(company.id)
              navigate(`/company/${company.id}/management/roadmap`)
            }}
          >
            <span
              className="company-list__accent"
              style={{
                background: `linear-gradient(180deg, ${company.accentFrom}, ${company.accentTo})`,
              }}
            />
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
        )
      })}
    </div>
  )
}

export default CompanyList
