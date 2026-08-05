import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False during SSR and the hydration pass, true afterwards.
 *
 * Use to gate rendering on values that only exist in the browser (resolved
 * theme, locale formatting) without a setState-in-effect round trip.
 */
export function useMounted(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false
  );
}
