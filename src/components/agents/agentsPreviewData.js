// STATIC sample data for the right-hand panel of the Agents tab (a preview of the future scheduling agent). Nothing here is read from the app;
// when the agent exists this file is what gets replaced by an API call.

export const SCHEDULED_TASKS = [
  { id: 'task-1', name: 'La Mayorista weekly refresh', status: 'Awaiting approval', tone: 'warn', when: 'Mondays, 6:00 AM · not active yet', actions: [] },
  { id: 'task-2', name: 'Aviation fuel prices download', status: 'Active', tone: 'ok', when: 'Daily, 7:00 AM · next run tomorrow', actions: ['Pause', 'Run now'] },
]

export const RECENT_RUNS = [
  { id: 'run-1', name: 'Fuel prices download', result: 'Done', tone: 'ok', detail: 'Today, 7:00 AM · 1 source updated', action: null },
  { id: 'run-2', name: 'Catalog refresh (manual)', result: 'Failed', tone: 'bad', detail: 'Yesterday · catalog service was not running', action: 'Retry this run' },
  { id: 'run-3', name: 'Tax multipliers fill', result: 'Done', tone: 'ok', detail: 'Monday, 2 Nov · changes can be undone', action: null },
]

export const AGENT_MAY = ['Read data in every module', 'Change data only after you approve', 'Never delete data or touch accounting']

// The two chips in the header of the center column (static as well).
export const AGENT_MODE = 'Mode: Ask before changing'
export const CATALOG_SERVICE_CHIP = 'Catalog service: running'
