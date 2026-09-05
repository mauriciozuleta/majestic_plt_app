import { useState } from 'react'
import { addEmployee, createPosition, updatePosition } from '../../../../../services/payroll'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'
import { downloadPayrollTemplate } from '../../../../../services/payrollTemplate'
import { readWorkbookRows } from '../../../../../services/excelImport'
import { parseFlatTemplate } from './importUtils'

/**
 * Owns the "Download format" / "Upload filled format" workflow: generate a
 * fill-in Excel template for the user to download, then read back whatever
 * file they upload and import it. A plain download/upload round trip rather
 * than watching a local file for changes — it doesn't depend on this app and
 * the spreadsheet editor running on the same machine, and there's no
 * background watch state to lose if the user navigates away mid-edit.
 */
export function useTemplateImport({ companyId, rows, defaultStartDate, reload }) {
  const [templateState, setTemplateState] = useState('idle')
  const [templateMessage, setTemplateMessage] = useState('')

  const handleImportTemplate = async (positions) => {
    setTemplateState('importing')
    setTemplateMessage('Importing the uploaded file…')

    try {
      const nodeIdByName = new Map(rows.map((row) => [row.office_name, row.node_id]))
      const existingByName = new Map(rows.map((row) => [row.office_name, row]))

      for (const position of positions) {
        const existing = existingByName.get(position.name)

        if (existing) {
          const updates = {}
          if (position.area) updates.area = position.area
          if (position.compByYear[0]) updates.year_salary = position.compByYear[0]
          if (Object.keys(updates).length > 0) {
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(existing.node_id, updates, 0)
          }
          for (let yearIndex = 1; yearIndex < position.compByYear.length; yearIndex += 1) {
            if (!position.compByYear[yearIndex]) continue
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(existing.node_id, { year_salary: position.compByYear[yearIndex] }, yearIndex)
          }

          const existingHireKeys = new Set(
            (existing.employees || []).map((employee) => `${employee.employee_name || ''}|${employee.start_date}`),
          )
          for (const hire of position.employees) {
            const key = `${hire.employee_name || ''}|${hire.start_date}`
            if (existingHireKeys.has(key)) continue
            // eslint-disable-next-line no-await-in-loop
            await addEmployee(
              existing.node_id,
              { employee_name: hire.employee_name, start_date: hire.start_date || defaultStartDate, end_date: hire.end_date },
              0,
            )
          }
        } else {
          const [firstHire, ...remainingHires] = position.employees
          // eslint-disable-next-line no-await-in-loop
          const created = await createPosition(
            companyId,
            {
              office_name: position.name,
              employee_name: firstHire?.employee_name || null,
              area: position.area || null,
              parent_node_id: null,
              year_salary: position.compByYear[0] || 0,
              start_date: firstHire?.start_date || defaultStartDate,
            },
            0,
          )
          for (let yearIndex = 1; yearIndex < position.compByYear.length; yearIndex += 1) {
            if (!position.compByYear[yearIndex]) continue
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(created.node_id, { year_salary: position.compByYear[yearIndex] }, yearIndex)
          }
          for (const hire of remainingHires) {
            // eslint-disable-next-line no-await-in-loop
            await addEmployee(
              created.node_id,
              { employee_name: hire.employee_name, start_date: hire.start_date || defaultStartDate, end_date: hire.end_date },
              0,
            )
          }
          nodeIdByName.set(position.name, created.node_id)
        }
      }

      // Second pass: every position (new or pre-existing) now has an id, so "Subordinated To"
      // can be wired up regardless of which order positions appeared in the sheet.
      for (const position of positions) {
        if (!position.parentName) continue
        const parentId = nodeIdByName.get(position.parentName)
        const childId = nodeIdByName.get(position.name)
        if (!parentId || !childId || parentId === childId) continue
        // eslint-disable-next-line no-await-in-loop
        await updatePosition(childId, { parent_node_id: parentId }, 0)
      }

      broadcastCompanyDataChange(companyId, 'payroll:import-template')
      await reload()
      setTemplateState('done')
      setTemplateMessage(`Imported ${positions.length} position${positions.length === 1 ? '' : 's'} from the uploaded file.`)
    } catch (err) {
      setTemplateState('error')
      setTemplateMessage(err.message || 'Something went wrong importing the file.')
    }
  }

  const handleDownloadFormat = async () => {
    setTemplateState('downloading')
    setTemplateMessage('Preparing the template…')
    try {
      await downloadPayrollTemplate(companyId)
      setTemplateState('idle')
      setTemplateMessage('')
    } catch (err) {
      setTemplateState('error')
      setTemplateMessage(err.message || 'Could not generate the template.')
    }
  }

  const handleUploadFormat = async (file) => {
    setTemplateState('importing')
    setTemplateMessage('Reading the uploaded file…')
    try {
      const jsonRows = await readWorkbookRows(file, 'Payroll')
      const parsed = parseFlatTemplate(jsonRows)

      if (parsed.positions.length === 0) {
        setTemplateState('error')
        setTemplateMessage(parsed.warnings[0] || 'This file has no rows to import.')
        return
      }
      await handleImportTemplate(parsed.positions)
    } catch (err) {
      setTemplateState('error')
      setTemplateMessage(err.message || 'Could not read that file.')
    }
  }

  return {
    templateState,
    templateMessage,
    handleDownloadFormat,
    handleUploadFormat,
    dismissTemplateStatus: () => setTemplateState('idle'),
  }
}
