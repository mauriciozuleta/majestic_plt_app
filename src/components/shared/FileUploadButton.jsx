import { useRef } from 'react'

/** A button that looks like any other button but opens a native file picker
 * and hands back the chosen File — the reusable half of any "upload a
 * filled-in template" flow, independent of what's done with the file. */
function FileUploadButton({ label, accept, onFileSelected, className, disabled }) {
  const inputRef = useRef(null)

  return (
    <>
      <button type="button" className={className} disabled={disabled} onClick={() => inputRef.current?.click()}>
        {label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) onFileSelected(file)
        }}
      />
    </>
  )
}

export default FileUploadButton
