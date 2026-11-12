import './HsCodeCell.css'

// A product's HS code as the normalization module gave it (`product.hs`, backend/catalog_normalization/hs.py): "<ISO2><6-digit HS>" or a warning label.
// No code -> red "No HS code" (the product cannot be traded until it has one); a 4-digit heading padded with zeros -> amber "Heading only"; a code nobody has
// reviewed yet -> a small neutral "AI" mark (not a warning).
function HsCodeCell({ hs }) {
  if (!hs?.hs6) {
    return (
      <span className="hs-cell">
        <span className="hs-cell__badge hs-cell__badge--none" title="This product has no HS code yet, so it cannot be traded. Add one from the red 'need data' pill.">
          No HS code
        </span>
      </span>
    )
  }
  return (
    <span className="hs-cell" title={hs.description || undefined}>
      <span>{hs.code || hs.hs6}</span>
      {hs.label === 'obsolete' && (
        <span className="hs-cell__badge hs-cell__badge--none" title="This code is from an older HS revision and no longer exists in HS 2022 (the current nomenclature). Replace it from the red 'need HS' pill.">
          Old code
        </span>
      )}
      {hs.label === 'heading_only' && (
        <span className="hs-cell__badge hs-cell__badge--heading" title="Only the 4-digit heading is known; the code is padded with zeros.">
          Heading only
        </span>
      )}
      {hs.ai_suggested && (
        <span className="hs-cell__mark" title="Suggested by AI, not yet confirmed by a person.">
          AI
        </span>
      )}
    </span>
  )
}

export default HsCodeCell
