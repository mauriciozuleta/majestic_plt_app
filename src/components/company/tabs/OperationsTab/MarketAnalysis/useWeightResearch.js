import { useState } from 'react'
import { researchProductWeights } from '../../../../../services/catalogNormalization'

// The "Research item weights" button of the product tables: asks the catalog normalization module to research, on the web, the weight of one item of the products
// whose unit is a count ("each", "per bunch"), then calls `onDone` so the table reloads its (now converted) catalog.
export function useWeightResearch(onDone) {
  const [researching, setResearching] = useState(false)

  const run = async (names) => {
    if (researching || !names.length) return
    setResearching(true)
    try {
      const { error } = await researchProductWeights(names, { limit: names.length })
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
