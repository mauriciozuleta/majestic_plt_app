const number = value => value == null ? '—' : Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })

export default function AircraftTable({ aircraft, selectedId, onSelect, database = false }) {
  return <div className="air-logistics__table-wrap"><table className="air-logistics__table">
    <thead><tr><th>Select</th>{database && <th>Source ID</th>}<th>Aircraft</th><th>Manufacturer</th><th className="num">MTOW (kg)</th><th className="num">Max Payload (kg)</th><th className="num">Fuel Capacity (gal)</th><th className="num">Fuel Burn (gal/h)</th><th className="num">Positions (Main / Lower)</th><th className="num">Cruise (kt)</th><th className="num">Range @ Max Payload (nm)</th>{database && <th>Fleet</th>}</tr></thead>
    <tbody>{aircraft.map(a => <tr key={a.id} className={selectedId === a.id ? 'is-selected' : ''} onClick={() => onSelect(selectedId === a.id ? null : a.id)}>
      <td><input type="checkbox" aria-label={`Select ${a.short_name}`} checked={selectedId === a.id} onClick={e => e.stopPropagation()} onChange={() => onSelect(selectedId === a.id ? null : a.id)} /></td>
      {database && <td>{a.source_aircraft_id ? (a.source_aircraft_id.replace('AI_FRESH24:', '') || 'Imported') : 'Local'}</td>}<td>{a.short_name} ({a.model})</td><td>{a.manufacturer}</td><td className="num">{number(a.mtow_kg)}</td><td className="num">{number(a.max_payload_kg)}</td><td className="num">{number(a.fuel_capacity_gal)}</td><td className="num">{number(a.fuel_burn_gal_hr)}</td><td className="num">{a.cargo_positions_main_deck} / {a.cargo_positions_lower_deck}</td><td className="num">{number(a.cruise_speed_kt)}</td><td className="num">{number(a.max_range_at_max_payload_nm)}</td>{database && <td>{a.in_fleet ? 'Selected' : 'Not selected'}</td>}
    </tr>)}</tbody>
  </table>{!aircraft.length && <p className="air-logistics__empty">{database ? 'No matching aircraft in the database.' : 'No aircraft selected. Add existing aircraft from the database below.'}</p>}</div>
}
