import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import './App.css'
import Header from './components/layout/Header/Header'
import Sidebar from './components/layout/Sidebar/Sidebar'
import Footer from './components/layout/Footer/Footer'
import HomeView from './components/home/HomeView'
import ControlDashboardView from './components/dashboard/ControlDashboardView'
import CommercialStructureView from './components/commercialStructure/CommercialStructureView'
import MarketAnalysisView from './components/marketAnalysis/MarketAnalysisView'
import GlobalTradeDataView from './components/globalTradeData/GlobalTradeDataView'
import SimulationsView, { SimulationsIndexRedirect } from './components/simulations/SimulationsView'
import SimParametersView from './components/simulations/SimParametersView'
import CompanyWorkspace, { CompanyIndexRedirect } from './components/company/CompanyWorkspace/CompanyWorkspace'
import OverviewTab from './components/company/tabs/OverviewTab/OverviewTab'
import ManagementTab from './components/company/tabs/ManagementTab/ManagementTab'
import FinancialTab from './components/company/tabs/FinancialTab/FinancialTab'
import OperationsTab from './components/company/tabs/OperationsTab/OperationsTab'
import SimulatorTab from './components/company/tabs/SimulatorTab/SimulatorTab'
import DriversTab from './components/company/tabs/DriversTab/DriversTab'
import DocumentationTab from './components/company/tabs/DocumentationTab/DocumentationTab'
import DocumentationView, { DocumentationIndexRedirect } from './components/documentation/DocumentationView'
import SettingsView from './components/company/tabs/ManagementTab/SettingsView/SettingsView'
import RagFilesView from './components/ragFiles/RagFilesView'
import TaxCalculatorView from './components/taxCalculator/TaxCalculatorView'
import ToolsView from './components/tools/ToolsView'
import AccountingHealthCheckCard from './components/company/tabs/ManagementTab/SettingsView/AccountingHealthCheckCard'
import AccountingAuditView from './components/accountingAudit/AccountingAuditView'
import CorporateStructureView from './components/corporateStructure/CorporateStructureView'
import { addCompany as createCompany, fetchCompanies } from './services/companies'
import { getCurrentUser } from './services/user'
import { useAppStore } from './store/useAppStore'

// Documentation moved to the sidebar; old company-tab links and remembered
// last-tab paths still resolve.
function DocumentationRedirect() {
  const { companyId } = useParams()
  return <Navigate to={`/documentation/${companyId}`} replace />
}

function Layout() {
  return (
    <div className="app-shell">
      <Header />

      <div className="app-shell__body">
        <Sidebar />

        <main className="app-shell__main">
          <div className="content-panel">
            <Routes>
              <Route path="/" element={<HomeView />} />
              <Route path="/corporate-structure" element={<CorporateStructureView />} />
              <Route path="/dashboard" element={<ControlDashboardView />} />
              <Route path="/commercial-structure" element={<CommercialStructureView />} />
              <Route path="/market-analysis" element={<MarketAnalysisView />} />
              <Route path="/market-analysis/:countryId" element={<MarketAnalysisView />} />
              <Route path="/global-trade-data" element={<GlobalTradeDataView />} />
              <Route path="/simulations" element={<SimulationsView />}>
                <Route index element={<SimulationsIndexRedirect />} />
                <Route path=":companyId" element={<Navigate to="parameters" replace />} />
                <Route path=":companyId/:sub" element={<SimParametersView />} />
              </Route>
              <Route path="/documentation" element={<DocumentationView />}>
                <Route index element={<DocumentationIndexRedirect />} />
                <Route path=":companyId" element={<DocumentationTab />} />
              </Route>
              <Route path="/tools" element={<ToolsView />}>
                <Route index element={<Navigate to="tax-calculator" replace />} />
                <Route path="tax-calculator" element={<TaxCalculatorView />} />
                <Route path="rag-files" element={<RagFilesView />} />
                <Route path="accounting-health-check" element={<AccountingHealthCheckCard />} />
              </Route>
              <Route path="/rag-files" element={<Navigate to="/tools/rag-files" replace />} />
              <Route path="/tax-calculator" element={<Navigate to="/tools/tax-calculator" replace />} />
              <Route path="/settings" element={<SettingsView />} />
              <Route path="/accounting-audit" element={<AccountingAuditView />} />

              <Route path="/company/:companyId" element={<CompanyWorkspace />}>
                <Route path="overview" element={<OverviewTab />} />
                <Route path="management/:sub" element={<ManagementTab />} />
                <Route path="management/:sub/:section" element={<ManagementTab />} />
                <Route path="financial/:sub" element={<FinancialTab />} />
                <Route path="financial/:sub/:section" element={<FinancialTab />} />
                <Route path="operations/market-analysis" element={<Navigate to="/market-analysis" replace />} />
                <Route path="operations/:sub" element={<OperationsTab />} />
                <Route path="operations" element={<Navigate to="commercial-operations" replace />} />
                <Route path="simulator" element={<SimulatorTab />} />
                <Route path="drivers" element={<DriversTab />} />
                <Route path="documentation" element={<DocumentationRedirect />} />
                <Route index element={<CompanyIndexRedirect />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>

      <Footer />
    </div>
  )
}

function App() {
  const setCurrentUser = useAppStore((state) => state.setCurrentUser)
  const setCompanies = useAppStore((state) => state.setCompanies)

  useEffect(() => {
    getCurrentUser().then((user) => {
      setCurrentUser(user)
    })
  }, [setCurrentUser])

  useEffect(() => {
    let cancelled = false

    const bootstrapCompanies = async () => {
      const companies = await fetchCompanies()
      if (cancelled) return

      if (companies.length > 0) {
        setCompanies(companies)
        return
      }

      const legacyStateRaw = window.localStorage.getItem('majestic-app-state')
      if (!legacyStateRaw) {
        setCompanies([])
        return
      }

      let legacyState = null
      try {
        legacyState = JSON.parse(legacyStateRaw)
      } catch {
        legacyState = null
      }

      const legacyCompanies = legacyState?.companies ?? []
      if (legacyCompanies.length === 0) {
        setCompanies([])
        return
      }

      const migratedCompanies = []
      for (const company of legacyCompanies) {
        migratedCompanies.push(await createCompany(company))
      }

      if (cancelled) return

      setCompanies(migratedCompanies)
      window.localStorage.removeItem('majestic-app-state')
    }

    bootstrapCompanies().catch(() => {
      if (!cancelled) setCompanies([])
    })

    return () => {
      cancelled = true
    }
  }, [setCompanies])

  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}

export default App
