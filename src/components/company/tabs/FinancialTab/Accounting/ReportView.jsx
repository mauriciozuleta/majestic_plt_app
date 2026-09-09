import ExportPdfButton from '../../../../shared/PdfExport/ExportPdfButton'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { reportToCsvRows, reportToPdfSpec } from './accountingReports'
import './Accounting.css'

function money(value) {
  const amount = Number(value) || 0
  const sign = amount < 0 ? '-' : ''
  return `${sign}$${Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function ReportView({ report, periodsCaption, csvFilename, balanced }) {
  const isEmpty = report.sections.length === 0

  const handleExportCsv = () => {
    const { headers, rows } = reportToCsvRows(report)
    downloadCsv(csvFilename, headers, rows)
  }

  return (
    <div className="accounting-view">
      <div className="accounting-view__toolbar">
        {typeof balanced === 'boolean' && (
          <span className={`accounting-view__badge ${balanced ? 'is-balanced' : 'is-unbalanced'}`}>
            {balanced ? 'Balanced' : 'Out of balance'}
          </span>
        )}
        <div className="accounting-view__export-actions">
          <button type="button" className="accounting-view__csv-btn" onClick={handleExportCsv}>
            Export CSV
          </button>
          <ExportPdfButton spec={reportToPdfSpec(report, periodsCaption)} label="Export PDF" />
        </div>
      </div>

      {isEmpty ? (
        <div className="accounting-view__status">No activity yet for this period.</div>
      ) : (
        <>
          {report.metrics.length > 0 && (
            <div className="accounting-view__metrics">
              {report.metrics.map((metric) => (
                <div key={metric.label} className={`accounting-view__metric ${metric.primary ? 'is-primary' : ''}`}>
                  <div className="accounting-view__metric-label">{metric.label}</div>
                  <div className="accounting-view__metric-value">{money(metric.amount)}</div>
                </div>
              ))}
            </div>
          )}

          {report.sections.map((section) => (
            <div key={section.key} className="report-view__section">
              <h4 className="report-view__section-title" style={{ color: section.color }}>
                {section.label}
              </h4>
              <table className="accounting-view__table">
                <tbody>
                  {section.rows.map((row) => (
                    <tr key={row.name}>
                      <td>{row.name}</td>
                      <td className="num">{money(row.amount)}</td>
                    </tr>
                  ))}
                  <tr className="report-view__subtotal-row" style={{ color: section.color }}>
                    <td>{section.label} — subtotal</td>
                    <td className="num">{money(section.subtotal)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

export default ReportView
