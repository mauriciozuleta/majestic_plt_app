import { useState } from 'react'
import { researchProductWeights } from '../../../../../services/catalogNormalization'

// The "Research item weights" button of the product tables: asks the catalog normalization module to research, on the web, the weight of one item of the products
// whose unit is a count ("each", "per bunch"), then calls `onDone` so the table reloads its (now converted) catalog.
const MAX_PER_CLICK = 12 // one batch: about 1 USD

export function useWeightResearch(onDone) {
  const [researching, setResearching] = useState(false)

  const run = async (names) => {
    if (researching || !names.length) return
    setResearching(true)
    try {
      // this spends Anthropic credits: ask the server for the estimate, show it, and run only what the person accepts (one run is capped on the server)
      const { estimate } = await researchProductWeights(names, { limit: MAX_PER_CLICK, dryRun: true })
      if (!estimate || !estimate.would_research) return
      const text = `Research the weight of ${estimate.would_research} product${estimate.would_research === 1 ? '' : 's'} on the web with Claude?\n\nEstimated cost: about $${estimate.estimated_usd.toFixed(2)} of Anthropic credits ($${estimate.usd_per_product.toFixed(2)} per product).\n${estimate.pending - estimate.would_research > 0 ? `${estimate.pending - estimate.would_research} more stay waiting (one run is capped).\n` : ''}\nFree options first: type the weights yourself in the "need data" form.`
      if (!window.confirm(text)) return
      const { error } = await researchProductWeights(names, { limit: MAX_PER_CLICK, confirmUsd: estimate.estimated_usd })
      onDone()
      if (error) window.alert(`Item-weight research: ${error}`)
    } catch (error) {
      window.alert(`Item-weight research failed: ${error.message}`)
    } finally {
      setResearching(false)
    }
  }

  return { researching, run }
}
