import './DeleteSeriesModal.css'

// window.confirm's OK/Cancel can't express 3 real outcomes without one of
// them hijacking Cancel to mean "show me another dialog" instead of "stop"
// — confusing, since Cancel should always mean the delete doesn't happen.
// This gives each outcome its own explicit button instead.
function DeleteSeriesModal({ entryLabel, siblingCount, onDeleteOne, onDeleteAll, onCancel }) {
  return (
    <div className="delete-series-modal__overlay" onClick={onCancel}>
      <div className="delete-series-modal" onClick={(event) => event.stopPropagation()}>
        <p className="delete-series-modal__message">
          "{entryLabel}" is part of a repeating series ({siblingCount} entries). What do you want to delete?
        </p>
        <div className="delete-series-modal__actions">
          <button type="button" className="delete-series-modal__cancel" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="delete-series-modal__one" onClick={onDeleteOne}>
            Just this one
          </button>
          <button type="button" className="delete-series-modal__all" onClick={onDeleteAll}>
            Delete all {siblingCount}
          </button>
        </div>
      </div>
    </div>
  )
}

export default DeleteSeriesModal
