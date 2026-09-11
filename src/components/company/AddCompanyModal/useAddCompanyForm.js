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
  const [countryCode, setCountryCode] = useState('')
  const [countryName, setCountryName] = useState('')
  const [currencyCode, setCurrencyCode] = useState('')
  const [currencyName, setCurrencyName] = useState('')
  const [accentFrom, setAccentFrom] = useState('#35D399')
  const [accentTo, setAccentTo] = useState('#0EA5E9')
  const [previewUrl, setPreviewUrl] = useState('')
  const [error, setError] = useState('')

  const resetForm = useCallback((initialCompany) => {
    setName(initialCompany?.name || '')
    setCompanyType(initialCompany?.companyType || 'LLC')
    setCompanyDependency(initialCompany?.companyDependency || 'Stand-alone')
    setSelectedParentId(initialCompany?.parentCompanyId || '')
    setCountryCode(initialCompany?.countryCode || '')
    setCountryName(initialCompany?.countryName || '')
    setCurrencyCode(initialCompany?.currencyCode || '')
    setCurrencyName(initialCompany?.currencyName || '')
    setAccentFrom(initialCompany?.accentFrom || '#35D399')
    setAccentTo(initialCompany?.accentTo || '#0EA5E9')
    setPreviewUrl(initialCompany?.logo || '')
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
      countryCode,
      countryName,
      currencyCode,
      currencyName,
      accentFrom,
      accentTo,
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
    countryCode,
    setCountryCode,
    countryName,
    setCountryName,
    currencyCode,
    setCurrencyCode,
    currencyName,
    setCurrencyName,
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
