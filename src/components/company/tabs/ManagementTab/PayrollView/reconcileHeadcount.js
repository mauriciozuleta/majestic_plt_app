import { employeeMonthlyActive } from './monthMath'

/**
 * Given a position's current roster and a hand-edited target headcount curve
 * for one year (12 numbers), works out the minimal set of seat changes that
 * would make the roster match that curve — new seats where the number goes
 * up, and an end date on the most-recently-hired active seat(s) where it
 * goes down (last hired, first let go).
 *
 * Returns a plan of primitive actions rather than mutating anything, so the
 * math can be tested and reviewed independently of the API calls that
 * execute it.
 *
 *   endMonth: 1-12, the last active month (a seat ending at endMonth=0 means
 *   "ended before this year even started" — handled by the caller as
 *   end_projection_year = selectedYear - 1 instead of a month).
 */
export function reconcileHeadcount(employees, targetMonths, selectedYear, calendarMode) {
  const pool = (employees || []).map((employee) => ({
    kind: 'existing',
    employee,
    months: employeeMonthlyActive(employee, selectedYear, calendarMode),
  }))

  const ends = [] // { kind: 'existing', employeeId, endMonth } | { kind: 'pending', pendingId, endMonth }
  const adds = [] // { pendingId, startMonth, endMonth }
  let pendingSeq = 0

  for (let index = 0; index < 12; index += 1) {
    const activeNow = pool.filter((seat) => seat.months[index] && !seat.months.__ended)
    const currentCount = activeNow.filter((seat) => seat.months[index]).length
    const target = targetMonths[index] ?? 0

    if (target > currentCount) {
      const need = target - currentCount
      for (let n = 0; n < need; n += 1) {
        pendingSeq += 1
        const pendingId = `pending-${pendingSeq}`
        const months = new Array(12).fill(false)
        for (let k = index; k < 12; k += 1) months[k] = true
        const seat = { kind: 'pending', pendingId, months }
        pool.push(seat)
        adds.push({ pendingId, startMonth: index + 1, endMonth: null })
      }
    } else if (target < currentCount) {
      const excess = currentCount - target
      const activeSeats = pool.filter((seat) => seat.months[index])
      const sorted = [...activeSeats].sort((a, b) => {
        const startA = a.kind === 'existing' ? String(a.employee.start_date) : '9999'
        const startB = b.kind === 'existing' ? String(b.employee.start_date) : '9999'
        return startB.localeCompare(startA) // most recently started first
      })
      for (let n = 0; n < excess; n += 1) {
        const victim = sorted[n]
        if (!victim) continue
        for (let k = index; k < 12; k += 1) victim.months[k] = false
        if (victim.kind === 'existing') {
          ends.push({ kind: 'existing', employeeId: victim.employee.id, endMonth: index })
        } else {
          const pendingAdd = adds.find((a) => a.pendingId === victim.pendingId)
          if (pendingAdd) pendingAdd.endMonth = index
        }
      }
    }
  }

  return { adds, ends }
}
