export const openLogoPicker = (inputRef) => {
  if (!inputRef.current) return
  inputRef.current.click()
}

export const makeLogoPreview = (file) => {
  if (!file) return null

  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('Failed to read image file'))
    reader.readAsDataURL(file)
  })
}
