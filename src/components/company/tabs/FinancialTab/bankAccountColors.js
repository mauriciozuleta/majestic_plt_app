// Deterministic per-account color so a bank account keeps the same
// identifying font color everywhere it's shown (list, ledger, dropdowns) —
// hashing the account id means it stays stable across reloads without
// needing to persist a color choice anywhere.
function hashToHue(id) {
  let hash = 0
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0
  }
  return hash % 360
}

export function colorForBankAccount(accountId) {
  const hue = hashToHue(String(accountId ?? ''))
  return `hsl(${hue}, 72%, 68%)`
}
