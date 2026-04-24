/**
 * Lightweight product analytics hook. Wire GA4 by loading gtag and defining `window.gtag`,
 * or extend this module to POST to your own collector.
 *
 * In development, events log to the console only.
 */
export function trackEvent(
  name: string,
  params?: Record<string, string | number | boolean>
): void {
  if (typeof window === "undefined") return;

  if (process.env.NODE_ENV === "development") {
    console.debug("[analytics]", name, params ?? {});
  }

  const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void })
    .gtag;
  if (typeof gtag === "function") {
    gtag("event", name, params ?? {});
  }
}
