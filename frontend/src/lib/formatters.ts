export function formatNumber(value: number | undefined | null, decimals: number = 2): string {
  if (value === undefined || value === null) return '-'
  return value.toFixed(decimals)
}

export function formatPercent(value: number | undefined | null, decimals: number = 2): string {
  if (value === undefined || value === null) return '-'
  return `${value.toFixed(decimals)}%`
}

export function formatCurrency(value: number | undefined | null): string {
  if (value === undefined || value === null) return '-'
  
  if (value >= 1e12) {
    return `$${(value / 1e12).toFixed(2)}T`
  } else if (value >= 1e9) {
    return `$${(value / 1e9).toFixed(2)}B`
  } else if (value >= 1e6) {
    return `$${(value / 1e6).toFixed(2)}M`
  } else if (value >= 1e3) {
    return `$${(value / 1e3).toFixed(2)}K`
  }
  
  return `$${value.toFixed(2)}`
}

export function formatVolume(value: number | undefined | null): string {
  if (value === undefined || value === null) return '-'
  
  if (value >= 1e9) {
    return `${(value / 1e9).toFixed(2)}B`
  } else if (value >= 1e6) {
    return `${(value / 1e6).toFixed(2)}M`
  } else if (value >= 1e3) {
    return `${(value / 1e3).toFixed(2)}K`
  }
  
  return value.toString()
}

export function getPriceChangeColor(value: number | undefined | null): string {
  if (value === undefined || value === null) return 'text-slate-400'
  return value >= 0 ? 'text-positive' : 'text-negative'
}
