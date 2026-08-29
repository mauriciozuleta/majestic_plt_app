import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import Header from './components/layout/Header/Header'
import Sidebar from './components/layout/Sidebar/Sidebar'
import Footer from './components/layout/Footer/Footer'
import HomeView from './components/home/HomeView'
import ControlDashboardView from './components/dashboard/ControlDashboardView'
import SimulationsView from './components/simulations/SimulationsView'
import CompanyWorkspace from './components/company/CompanyWorkspace/CompanyWorkspace'
import ManagementTab from './components/company/tabs/ManagementTab/ManagementTab'
import FinancialTab from './components/company/tabs/FinancialTab/FinancialTab'
import OperationsTab from './components/company/tabs/OperationsTab/OperationsTab'
import SimulatorTab from './components/company/tabs/SimulatorTab/SimulatorTab'
import DriversTab from './components/company/tabs/DriversTab/DriversTab'
import DocumentationTab from './components/company/tabs/DocumentationTab/DocumentationTab'
import SettingsView from './components/company/tabs/ManagementTab/SettingsView/SettingsView'
import { addCompany as createCompany, fetchCompanies } from './services/companies'
import { getCurrentUser } from './services/user'
import { useAppStore } from './store/useAppStore'

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
              <Route path="/dashboard" element={<ControlDashboardView />} />
              <Route path="/simulations" element={<SimulationsView />} />
              <Route path="/settings" element={<SettingsView />} />

              <Route path="/company/:companyId" element={<CompanyWorkspace />}>
                <Route path="management/:sub" element={<ManagementTab />} />
                <Route path="financial/:sub" element={<FinancialTab />} />
                <Route path="operations" element={<OperationsTab />} />
                <Route path="simulator" element={<SimulatorTab />} />
                <Route path="drivers" element={<DriversTab />} />
                <Route path="documentation" element={<DocumentationTab />} />
                <Route index element={<Navigate to="management/roadmap" replace />} />
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
