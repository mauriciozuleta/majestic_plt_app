import * as XLSX from 'xlsx'

/** Reads a user-uploaded .xlsx File into plain row objects (header row as
 * keys) — the client-side half of any "upload a filled-in template" flow.
 * Pass `sheetName` when the template has more than one sheet and a specific
 * one holds the data; otherwise the first sheet is used. */
export async function readWorkbookRows(file, sheetName) {
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array' })
  const sheet = (sheetName && workbook.Sheets[sheetName]) || workbook.Sheets[workbook.SheetNames[0]]
  return XLSX.utils.sheet_to_json(sheet, { defval: '' })
}
