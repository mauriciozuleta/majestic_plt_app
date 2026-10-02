import { useEffect, useRef, useState } from 'react'

export default function SaveConfigurationDialog({ initialName, asNew, onSave, onClose }) {
  const dialogRef = useRef(null)
  const inputRef = useRef(null)
  const [name, setName] = useState(initialName)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    dialogRef.current.showModal()
    inputRef.current.focus()
    inputRef.current.select()
  }, [])

  const submit = async e => {
    e.preventDefault()
    if (saving || !name.trim()) return
    setSaving(true)
    setError('')
    try {
      await onSave(name.trim())
      onClose()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return <dialog ref={dialogRef} className="packer packer-modal packer-save-dialog" aria-labelledby="save-configuration-title" onCancel={e => { e.preventDefault(); if (!saving) onClose() }}>
    <form onSubmit={submit}>
      <h2 id="save-configuration-title">{asNew ? 'Save as new configuration' : 'Save configuration'}</h2>
      <p className="packer-muted">Save the aircraft setup, box catalogue, allocations, packing rules and load details to the database.</p>
      <label className="packer-field"><span>Configuration name</span><input ref={inputRef} value={name} onChange={e => setName(e.target.value)} maxLength={200} required disabled={saving} placeholder="Enter a configuration name" /></label>
      {error && <p className="packer-error" role="alert">{error}</p>}
      <div className="packer-modal-footer"><button type="button" disabled={saving} onClick={onClose}>Cancel</button><button className="packer-primary" type="submit" disabled={saving || !name.trim()}>{saving ? 'Saving…' : 'Save changes'}</button></div>
    </form>
  </dialog>
}
