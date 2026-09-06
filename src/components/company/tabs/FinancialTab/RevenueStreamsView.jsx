import './RevenueStreamsView.css'

function RevenueStreamsView() {
  return (
    <div className="panel-surface revenue-streams-view">
      <h3>Revenue/COS</h3>
      <p>Break revenue down by stream.</p>
      <button type="button" className="revenue-streams-view__add-btn">
        + Add New Revenue Stream
      </button>
    </div>
  )
}

export default RevenueStreamsView
