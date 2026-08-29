import { useCallback, useRef, useState } from 'react'
import { makeLogoPreview, openLogoPicker } from '../../../utils/logoUpload'

export const legalTypes = [
  'LLC',
  'C-Corp',
  'S-Corp',
  'Partnership',
  'Sole Proprietorship',
  'Nonprofit',
  'LLP',
  'Other',
]

export const dependencyOptions = ['Stand-alone', 'Children']

export function useAddCompanyForm() {
  const inputRef = useRef(null)
  const [name, setName] = useState('')
  const [companyType, setCompanyType] = useState('LLC')
  const [companyDependency, setCompanyDependency] = useState('Stand-alone')
  const [selectedParentId, setSelectedParentId] = useState('')
  const [previewUrl, setPreviewUrl] = useState('')
  const [error, setError] = useState('')

  const resetForm = useCallback(() => {
    setName('')
    setCompanyType('LLC')
    setCompanyDependency('Stand-alone')
    setSelectedParentId('')
    setPreviewUrl('')
    setError('')

    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }, [])

  const handleSelectLogo = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    const preview = await makeLogoPreview(file)
    setPreviewUrl(preview)
  }

  const handleSubmit = (onSubmit, companies = []) => {
    const trimmedName = name.trim()

    if (!trimmedName) {
      setError('Company name is required.')
      return
    }

    setError('')
    onSubmit({
      name: trimmedName,
      logo: previewUrl || '',
      companyType,
      companyDependency,
      parentCompanyId: companyDependency === 'Children' ? selectedParentId : null,
      companies,
    })
  }

  return {
    name,
    setName,
    companyType,
    setCompanyType,
    companyDependency,
    setCompanyDependency,
    selectedParentId,
    setSelectedParentId,
    previewUrl,
    setPreviewUrl,
    error,
    inputRef,
    resetForm,
    openLogoPicker: () => openLogoPicker(inputRef),
    handleSelectLogo,
    handleSubmit,
  }
}
