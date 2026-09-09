export const PAPER_SIZES = {
  letter: { label: 'Letter', width: 8.5, height: 11 },
  legal: { label: 'Legal', width: 8.5, height: 14 },
}

const DEFAULT_MARGIN_IN = 0.55

export function computePageBox(paperSize, orientation) {
  const dims = PAPER_SIZES[paperSize] ?? PAPER_SIZES.letter
  const isLandscape = orientation === 'landscape'
  return {
    widthIn: isLandscape ? dims.height : dims.width,
    heightIn: isLandscape ? dims.width : dims.height,
    marginIn: DEFAULT_MARGIN_IN,
  }
}
