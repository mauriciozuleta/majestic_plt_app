import './AddCompanyModal.css'
import { IconEdit, IconUpload, IconX } from '@tabler/icons-react'
import { useEffect } from 'react'
import { dependencyOptions, legalTypes, useAddCompanyForm } from './useAddCompanyForm'
import { useAppStore } from '../../../store/useAppStore'

function AddCompanyModal({ isOpen, onClose, onSave }) {
  const companies = useAppStore((state) => state.companies)
  const {
    name,
    setName,
    companyType,
    setCompanyType,
    companyDependency,
    setCompanyDependency,
    selectedParentId,
    setSelectedParentId,
    previewUrl,
    error,
    inputRef,
    resetForm,
    openLogoPicker,
    handleSelectLogo,
    handleSubmit,
  } = useAddCompanyForm()

  useEffect(() => {
    if (isOpen) {
      resetForm()
    }
  }, [isOpen, resetForm])

  if (!isOpen) return null

  return (
    <div className="add-company-modal__overlay" onClick={onClose}>
      <div className="add-company-modal" onClick={(event) => event.stopPropagation()}>
        <div className="add-company-modal__header">
          <h3>Add company</h3>
          <button type="button" className="add-company-modal__close" onClick={onClose} aria-label="Close modal">
            <IconX size={16} stroke={1.8} />
          </button>
        </div>

        <div className="add-company-modal__field">
          <label htmlFor="company-name">Company name</label>
          <input
            id="company-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Enter company name"
          />
        </div>

        <div className="add-company-modal__field">
          <label htmlFor="company-type">Company type</label>
          <select id="company-type" value={companyType} onChange={(event) => setCompanyType(event.target.value)}>
            {legalTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div className="add-company-modal__field">
          <label htmlFor="company-dependency">Company dependency</label>
          <select
            id="company-dependency"
            value={companyDependency}
            onChange={(event) => setCompanyDependency(event.target.value)}
          >
            {dependencyOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        {companyDependency === 'Children' && (
          <div className="add-company-modal__field">
            <label htmlFor="parent-company">Child of</label>
            <select
              id="parent-company"
              value={selectedParentId}
              onChange={(event) => setSelectedParentId(event.target.value)}
            >
              <option value="">Select a company</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="add-company-modal__field">
          <label>Logo</label>
          <div className="add-company-modal__upload-row">
            <button type="button" className="add-company-modal__upload" onClick={openLogoPicker}>
              <IconUpload size={16} stroke={1.8} />
              Upload logo
            </button>
            {previewUrl && (
              <button
                type="button"
                className="add-company-modal__preview-card"
                onClick={openLogoPicker}
                aria-label="Edit company logo"
                title="Edit logo"
              >
                <img src={previewUrl} alt="Company preview" className="add-company-modal__preview" />
                <span className="add-company-modal__preview-edit">
                  <IconEdit size={13} stroke={2} />
                </span>
              </button>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="add-company-modal__file-input"
            onChange={handleSelectLogo}
          />
        </div>

        {error && <div className="add-company-modal__error">{error}</div>}

        <div className="add-company-modal__actions">
          <button type="button" className="add-company-modal__cancel" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="add-company-modal__save"
            onClick={() => {
              handleSubmit((payload) => {
                onSave(payload)
                onClose()
              }, companies)
            }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

export default AddCompanyModal
