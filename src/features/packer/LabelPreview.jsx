import { useEffect, useState } from 'react'
import { request } from './api'
import { fmt } from './format'

export default function LabelPreview({ boxes, plan }) {
  const [barcodes, setBarcodes] = useState({})
  const ids = JSON.stringify(boxes.slice(0, 6).map(b => b.box_id))
  useEffect(() => {
    const controller = new AbortController()
    request('/barcodes', { ids: JSON.parse(ids) }, { signal: controller.signal })
      .then(setBarcodes).catch(() => { /* PDF exports remain available if image preview fails. */ })
    return () => controller.abort()
  }, [ids])
  return <details><summary>Label preview · first {Math.min(6, boxes.length)}</summary><div className="packer-label-grid">{boxes.slice(0, 6).map(b => <div className="packer-label" key={b.box_id}>
    <strong>{b.deck === 'main' ? 'MD' : 'LWR'} {b.position} · {b.box_id}</strong><span>Layer {b.layer} · Slot {b.slot} · {b.aircraft}</span><span>{b.box_type} · {b.dims_cm} cm {b.upright ? ' · THIS SIDE UP' : ''}</span><span>{fmt(b.actual_kg)} actual / {fmt(b.volume_kg)} volume / {fmt(b.chargeable_kg)} chargeable kg</span><span>{plan.name} · {plan.manifest.flight}</span>
    {barcodes[b.box_id] ? <img alt={`Code 128: ${b.box_id}`} src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(barcodes[b.box_id])}`} /> : <small>Code 128 barcode generated in PDF</small>}
  </div>)}</div></details>
}
