const CHAR_WIDTH_EM = 0.62 // approx width of one tabular-mono digit, in em
const CELL_H_PADDING_PX = 10 // combined left+right cell padding reserved, in px
const MIN_FONT_PX = 7
const MAX_FONT_PX = 15

// Solves for the largest font size that still lets the longest formatted
// number in the table fit inside its column, given the real pixel width
// available on the chosen paper size/orientation. This replaces guessing a
// font size and hoping the numbers fit — instead the numbers are guaranteed
// to fit (down to MIN_FONT_PX) because the size is derived from the columns'
// actual pixel width.
export function computeLedgerMetrics({ columnCount, maxValueLength, availableWidthPx }) {
  const namePct = columnCount <= 6 ? 24 : columnCount <= 9 ? 19 : columnCount <= 12 ? 15 : 12
  const nameColWidthPx = availableWidthPx * (namePct / 100)
  const numColCount = columnCount + 1
  const numColWidthPx = (availableWidthPx - nameColWidthPx) / numColCount
  const usableTextWidthPx = Math.max(numColWidthPx - CELL_H_PADDING_PX, 4)

  const rawFontPx = usableTextWidthPx / (Math.max(maxValueLength, 1) * CHAR_WIDTH_EM)
  const fontPx = Math.min(MAX_FONT_PX, Math.max(MIN_FONT_PX, rawFontPx))

  const fontSize = `${(fontPx / 16).toFixed(3)}rem`
  const vPad = Math.max(fontPx * 0.32, 3)
  const hPad = CELL_H_PADDING_PX / 2
  const cellPadding = `${vPad.toFixed(1)}px ${hPad.toFixed(1)}px`
  const rowHeightPx = fontPx * 1.35 + vPad * 2 + 1

  return {
    fontPx,
    fontSize,
    namePct,
    cellPadding,
    rowHeightPx,
    numColWidthPx,
  }
}
