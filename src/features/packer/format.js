export const colors = ['#e8a33d', '#35d399', '#6aa9f0', '#ba8ce8', '#f18b83', '#75cbd3']
export const fmt = (value, digits = 1) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits })
