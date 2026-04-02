const MAX_HISTORY_LENGTH = 20;

/**
 * Per-symbol conversation manager.
 * Tracks conversation history keyed by symbol+resolution.
 * Resets automatically when the user switches chart context.
 */
class ConversationManager {
  constructor() {
    /** @type {Map<string, Array<{role: string, content: string}>>} */
    this.histories = new Map();
    this.activeKey = null;
  }

  _makeKey(symbol, resolution) {
    return `${symbol}:${resolution}`;
  }

  /**
   * Get or create conversation for the given chart context.
   * Returns { messages, switched } where switched=true if context changed.
   */
  getHistory(symbol, resolution) {
    const key = this._makeKey(symbol, resolution);
    const switched = this.activeKey !== null && this.activeKey !== key;
    this.activeKey = key;

    if (!this.histories.has(key)) {
      this.histories.set(key, []);
    }
    return { messages: this.histories.get(key), switched };
  }

  addMessage(role, content) {
    if (!this.activeKey) return;
    const history = this.histories.get(this.activeKey);
    history.push({ role, content });
    if (history.length > MAX_HISTORY_LENGTH) {
      history.splice(0, history.length - MAX_HISTORY_LENGTH);
    }
  }

  reset(symbol, resolution) {
    if (symbol && resolution) {
      this.histories.delete(this._makeKey(symbol, resolution));
    } else if (this.activeKey) {
      this.histories.delete(this.activeKey);
    }
  }

  resetAll() {
    this.histories.clear();
    this.activeKey = null;
  }

  get activeSymbol() {
    return this.activeKey?.split(':')[0] || null;
  }

  get activeResolution() {
    return this.activeKey?.split(':')[1] || null;
  }
}

export const conversation = new ConversationManager();
