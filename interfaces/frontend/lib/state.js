// Store pub/sub mínimo (sem dependências, testável em Node).
export function createStore(initial = {}) {
  let state = { busy: false, muted: false, currentThread: null, ...initial };
  const subs = new Set();
  return {
    get: () => state,
    set(patch) {
      state = { ...state, ...patch };
      for (const fn of subs) fn(state);
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}
