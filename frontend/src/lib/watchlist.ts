/**
 * Watchlist management using localStorage
 */

const WATCHLIST_KEY = 'stock-watchlist'

export function getWatchlist(): string[] {
  try {
    const stored = localStorage.getItem(WATCHLIST_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

export function addToWatchlist(ticker: string): void {
  const watchlist = getWatchlist()
  if (!watchlist.includes(ticker.toUpperCase())) {
    watchlist.push(ticker.toUpperCase())
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(watchlist))
  }
}

export function removeFromWatchlist(ticker: string): void {
  const watchlist = getWatchlist()
  const filtered = watchlist.filter(t => t !== ticker.toUpperCase())
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(filtered))
}

export function isInWatchlist(ticker: string): boolean {
  return getWatchlist().includes(ticker.toUpperCase())
}

export function toggleWatchlist(ticker: string): boolean {
  if (isInWatchlist(ticker)) {
    removeFromWatchlist(ticker)
    return false
  } else {
    addToWatchlist(ticker)
    return true
  }
}
