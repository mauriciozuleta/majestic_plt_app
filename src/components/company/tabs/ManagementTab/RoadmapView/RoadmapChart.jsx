import { getBarGeometry, getDateRange, getDayWidth, getHeaderSegments } from './roadmapLayout'
import { formatCalendarDateCompact } from '../../../../../services/calendarDates'
import './RoadmapChart.css'

const MIN_ZOOM_SCALE = 0.5
const MAX_ZOOM_SCALE = 2.2

function clampZoomScale(nextScale) {
  return Math.max(MIN_ZOOM_SCALE, Math.min(MAX_ZOOM_SCALE, nextScale))
}

function RoadmapChart({ tasks, zoom, zoomScale, onZoomScaleChange, calendarMode, selectedTaskId, onSelectTask, companies }) {
  const { start: rangeStart, end: rangeEnd } = getDateRange(tasks, calendarMode)
  const dayWidth = Math.max(2, Math.round(getDayWidth(zoom) * zoomScale))
  const segmentDays = zoom === 'Month' ? 30 : 7
  const segmentStepWidth = segmentDays * dayWidth
  const headerSegments = getHeaderSegments(rangeStart, rangeEnd, zoom, dayWidth, calendarMode)
  const timelineWidth = headerSegments.reduce((sum, segment) => sum + segment.width, 0)

  const handleWheelZoom = (event) => {
    event.preventDefault()
    const delta = event.deltaY < 0 ? 0.1 : -0.1
    onZoomScaleChange((previous) => clampZoomScale(Number(previous) + delta))
  }

  return (
    <div className="roadmap-chart">
      <div className="roadmap-chart__corner-name">Name</div>
      <div className="roadmap-chart__corner-begin">Begin</div>
      <div className="roadmap-chart__corner-end">End</div>
      <div className="roadmap-chart__zoom-controls" onWheel={handleWheelZoom}>
        <button type="button" onClick={() => onZoomScaleChange((previous) => clampZoomScale(Number(previous) - 0.1))} aria-label="Zoom out timeline">
          ←
        </button>
        <span>Zoom</span>
        <button type="button" onClick={() => onZoomScaleChange((previous) => clampZoomScale(Number(previous) + 0.1))} aria-label="Zoom in timeline">
          →
        </button>
      </div>
      <div className="roadmap-chart__header" style={{ width: timelineWidth }} onWheel={handleWheelZoom}>
        {headerSegments.map((segment, index) => (
          <div key={`${segment.label}-${index}`} className="roadmap-chart__header-cell" style={{ width: segment.width }}>
            {segment.label}
          </div>
        ))}
      </div>

      {tasks.map((task) => {
        const { left, width } = getBarGeometry(task, rangeStart, dayWidth)
        const isSelected = task.id === selectedTaskId
        const barClassName = task.isGroupTask
          ? `roadmap-chart__bar roadmap-chart__bar--group ${isSelected ? 'is-selected' : ''}`
          : `roadmap-chart__bar ${isSelected ? 'is-selected' : ''}`

        return (
          <div className="roadmap-chart__row" key={task.id} onClick={() => onSelectTask(task.id)}>
            <div
              className={`roadmap-chart__cell-name ${isSelected ? 'is-selected' : ''}`}
              style={{ paddingLeft: `${10 + (task.depth || 0) * 16}px` }}
            >
              {task.name}
            </div>
            <div className="roadmap-chart__cell-date roadmap-chart__cell-date--begin">
              {formatCalendarDateCompact(task.start, calendarMode)}
            </div>
            <div className="roadmap-chart__cell-date roadmap-chart__cell-date--end">
              {formatCalendarDateCompact(task.end, calendarMode)}
            </div>
            <div
              className="roadmap-chart__timeline-row"
              onWheel={handleWheelZoom}
              style={{
                width: timelineWidth,
                '--roadmap-grid-step': `${segmentStepWidth}px`,
                '--roadmap-grid-substep': `${dayWidth}px`,
              }}
            >
              <div
                className={barClassName}
                style={{ left, width }}
                title={task.isGroupTask ? 'Group task' : `${task.progress}% progress`}
              >
                {!task.isGroupTask ? (
                  <div
                    className="roadmap-chart__bar-progress"
                    style={{ width: `${task.progress}%` }}
                    title={`${task.progress}% progress`}
                    aria-label={`${task.progress}% progress`}
                  />
                ) : null}
                <span className="roadmap-chart__bar-label">{task.name}</span>
                {task.linked_company_id ? (
                  <span className="roadmap-chart__bar-link">
                    {companies.find((company) => company.id === task.linked_company_id)?.name ?? 'Linked company'}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default RoadmapChart
