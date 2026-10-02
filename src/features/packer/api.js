import { API_BASE } from '../../services/apiBase'

export async function request(path, body, options = {}) {
  const response = await fetch(`${API_BASE}/api/packer${path}`, {
    ...options,
    method: options.method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const detail = Array.isArray(error.detail) ? error.detail.map(e => `${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ') : error.detail
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function download(planId, file, params) {
  const response = await fetch(`${API_BASE}/api/packer/plans/${planId}/${file}?${new URLSearchParams(params)}`)
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || 'Export failed')
  }
  const url = URL.createObjectURL(await response.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = `cargo-${file}`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

export const newPlan = (companyId, aircraft) => ({
  company_id: companyId, name: 'New load plan', aircraft_id: aircraft.id, aircraft,
  box_types: [
    { name: 'Produce carton', l: 60, w: 40, h: 25, kg: 14, max_layers: 30, upright: true },
    { name: 'Flower box', l: 100, w: 50, h: 30, kg: 12, max_layers: 30, upright: true },
  ],
  alloc: { main: {}, lower: {} },
  settings: { divisor: 6000, min_support: 80, interlock: true, order: 'heavy', strict_density: true,
    id_prefix: 'BOX-', id_digits: 4, label_format: 'letter10',
    main: { side_clearance: 2.5, end_clearance: 1, lean: false, lean_min_support: 50 },
    lower: { side_clearance: 3, end_clearance: 3, lean: true, lean_min_support: 50 } },
  manifest: { leader: '', flight: '', registration: '', date: new Date().toISOString().slice(0, 10), notes: '' }, version: 0,
})
