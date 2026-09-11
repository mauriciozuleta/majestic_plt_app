import { useState } from 'react'
import { createPosition, updatePosition } from '../../../../../services/payroll'
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
export function useTemplateImport({ companyId, rows, payrollLevels, defaultStartDate, reload }) {
  const [templateState, setTemplateState] = useState('idle')
  const [templateMessage, setTemplateMessage] = useState('')

  const handleImportTemplate = async (positions) => {
    setTemplateState('importing')
    setTemplateMessage('Importing the uploaded file…')

    try {
      // A position's identity is (name, "Subordinated To"), not the name
      // alone — "Secretary / Assistant" answering to five different
      // managers is five distinct positions that happen to share a label,
      // not one position repeated (see importUtils.js). `nodeIdByName`
      // (plain name -> id) is used only to resolve a PARENT reference,
      // where names are expected to be unique in practice; a duplicate-
      // named position's own identity always goes through the composite
      // key so each one gets wired to its own correct parent, not
      // whichever same-named node happened to be created/matched last.
      const nodeNameById = new Map(rows.map((row) => [row.node_id, row.office_name]))
      const nodeIdByName = new Map(rows.map((row) => [row.office_name, row.node_id]))
      const existingByComposite = new Map(
        rows.map((row) => [`${row.office_name}::${row.parent_node_id ? nodeNameById.get(row.parent_node_id) || '' : ''}`, row]),
      )
      const nodeIdByComposite = new Map()
      const levelByCode = new Map((payrollLevels || []).map((level) => [level.level, level]))

      for (const position of positions) {
        const composite = `${position.name}::${position.parentName}`
        const existing = existingByComposite.get(composite)
        const matchedLevel = position.level ? levelByCode.get(position.level) : null
        // "Compensation (custom)" always wins over the level's standard
        // figure when the user filled it in — that's the one column meant
        // to override compensation for a single position.
        const resolvedSalary = position.customSalary ?? (matchedLevel ? matchedLevel.yearly : null)

        if (existing) {
          const updates = {}
          if (position.area) updates.area = position.area
          if (position.location) updates.location = position.location
          if (matchedLevel) updates.payroll_level = matchedLevel.level
          if (resolvedSalary !== null) updates.year_salary = resolvedSalary
          if (Object.keys(updates).length > 0) {
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(existing.node_id, updates, 0)
          }
          nodeIdByComposite.set(composite, existing.node_id)
          nodeIdByName.set(position.name, existing.node_id)
        } else {
          // eslint-disable-next-line no-await-in-loop
          const created = await createPosition(
            companyId,
            {
              office_name: position.name,
              employee_name: null,
              area: position.area || null,
              location: position.location || null,
              parent_node_id: null,
              year_salary: resolvedSalary ?? 0,
              payroll_level: matchedLevel ? matchedLevel.level : null,
              start_date: defaultStartDate,
            },
            0,
          )
          nodeIdByComposite.set(composite, created.node_id)
          nodeIdByName.set(position.name, created.node_id)
        }
      }

      // Second pass: every position (new or pre-existing) now has an id, so "Subordinated To"
      // can be wired up regardless of which order positions appeared in the sheet. Each
      // position's OWN id comes from the composite map, so two same-named positions each
      // get wired to their own parent rather than both collapsing onto one.
      for (const position of positions) {
        if (!position.parentName) continue
        const composite = `${position.name}::${position.parentName}`
        const childId = nodeIdByComposite.get(composite)
        const parentId = nodeIdByName.get(position.parentName)
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
