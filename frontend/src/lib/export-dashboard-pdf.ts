import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

let canvas2d: CanvasRenderingContext2D | null = null;

function getCanvas2d(): CanvasRenderingContext2D | null {
  if (typeof document === "undefined") {
    return null;
  }
  if (!canvas2d) {
    canvas2d = document.createElement("canvas").getContext("2d");
  }
  return canvas2d;
}

function camelToKebab(prop: string): string {
  return prop.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

/**
 * html2canvas cannot parse modern CSS color serializations (e.g. lab/oklch from
 * getComputedStyle). The 2D canvas context accepts them and re-serializes to
 * #hex/rgb, which the library can read.
 */
function toCanvasSafeColor(value: string | null | undefined): string | null {
  if (value == null) return null;
  const t = value.trim();
  if (
    t === "" ||
    t === "none" ||
    t === "transparent" ||
    t === "rgba(0, 0, 0, 0)"
  ) {
    return t;
  }
  const ctx = getCanvas2d();
  if (!ctx) return t;
  try {
    ctx.fillStyle = "#000000";
    ctx.fillStyle = t;
    const out = String(ctx.fillStyle);
    if (out.startsWith("#") || out.startsWith("rgb")) {
      return out;
    }
  } catch {
    /* use fallback below */
  }
  return t;
}

const MODERN_COLOR_FN = /(lab|oklch|lch|color)\(/i;

const COLOR_STYLE_PROPS: (keyof CSSStyleDeclaration)[] = [
  "color",
  "backgroundColor",
  "borderTopColor",
  "borderRightColor",
  "borderBottomColor",
  "borderLeftColor",
  "outlineColor",
  "textDecorationColor",
  "columnRuleColor",
  "fill",
  "stroke",
];

const EXTRA_SVG_KEBAB = ["stop-color", "flood-color", "lighting-color"] as const;

/**
 * Pairs the original and cloned nodes (same node order) and rewrites
 * color-related properties on the clone to rgb/#hex so html2canvas can parse them.
 */
function rewriteCloneColorsToSrgb(
  originalRoot: Element,
  cloneRoot: Element
): void {
  const origEls: Element[] = [originalRoot, ...originalRoot.querySelectorAll("*")];
  const cloneEls: Element[] = [cloneRoot, ...cloneRoot.querySelectorAll("*")];
  const n = Math.min(origEls.length, cloneEls.length);
  for (let i = 0; i < n; i += 1) {
    const orig = origEls[i];
    const copy = cloneEls[i] as Element & { style: CSSStyleDeclaration };
    if (!copy?.style || !orig.ownerDocument) continue;
    const style = getComputedStyle(orig);
    for (const prop of COLOR_STYLE_PROPS) {
      const raw = (style as CSSStyleDeclaration)[prop] as string | undefined;
      if (typeof raw !== "string" || !raw) continue;
      const safe = toCanvasSafeColor(raw);
      if (safe == null) continue;
      if (safe === raw && !MODERN_COLOR_FN.test(raw)) continue;
      copy.style.setProperty(camelToKebab(String(prop)), safe, "important");
    }
    for (const kebab of EXTRA_SVG_KEBAB) {
      const raw = style.getPropertyValue(kebab);
      if (!raw) continue;
      const safe = toCanvasSafeColor(raw);
      if (safe == null) continue;
      if (safe === raw && !MODERN_COLOR_FN.test(raw)) continue;
      copy.style.setProperty(kebab, safe, "important");
    }
    for (const shadowProp of ["box-shadow", "text-shadow"] as const) {
      const raw = style.getPropertyValue(shadowProp);
      if (raw && MODERN_COLOR_FN.test(raw)) {
        copy.style.setProperty(shadowProp, "none", "important");
      }
    }
  }
}

function sanitizeFilenamePart(name: string): string {
  return name
    .trim()
    .replace(/[/\\?%*:|"<>]/g, "-")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 72) || "workspace";
}

/**
 * Rasterizes a DOM subtree to a multi-page A4 PDF (portrait).
 * Temporarily opens `#workspace-full-briefing` if present so the full model output is included.
 */
export async function exportDashboardToPdf(
  root: HTMLElement,
  options: { workspaceName: string }
): Promise<void> {
  const details = document.getElementById(
    "workspace-full-briefing"
  ) as HTMLDetailsElement | null;
  const hadOpen = details?.open ?? false;
  if (details) {
    details.open = true;
  }

  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

  try {
    const canvas = await html2canvas(root, {
      scale: Math.min(2, window.devicePixelRatio || 2),
      useCORS: true,
      logging: false,
      backgroundColor: "#ffffff",
      windowWidth: root.scrollWidth,
      windowHeight: root.scrollHeight,
      onclone: (clonedDoc, clonedElement) => {
        clonedDoc.documentElement.classList.remove("dark");
        const cloneRoot =
          clonedElement ??
          (clonedDoc.querySelector(".dashboard-pdf-root") as HTMLElement | null);
        if (cloneRoot) {
          rewriteCloneColorsToSrgb(root, cloneRoot);
        }
        clonedDoc.querySelectorAll("[data-pdf-exclude]").forEach((el) => {
          el.remove();
        });
        const clonedRoot = clonedDoc.querySelector(
          ".dashboard-pdf-root"
        ) as HTMLElement | null;
        if (clonedRoot) {
          clonedRoot.style.background = "#ffffff";
          clonedRoot.style.color = "#0f172a";
        }
      },
    });

    const imgData = canvas.toDataURL("image/png");
    const pdf = new jsPDF({
      orientation: "portrait",
      unit: "pt",
      format: "a4",
    });

    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 36;
    const contentWidth = pageWidth - margin * 2;
    const usableHeight = pageHeight - margin * 2;
    const imgHeight = (canvas.height * contentWidth) / canvas.width;

    let offset = 0;
    pdf.addImage(imgData, "PNG", margin, margin - offset, contentWidth, imgHeight);
    let remaining = imgHeight - usableHeight;

    while (remaining > 0) {
      offset += usableHeight;
      pdf.addPage();
      pdf.addImage(imgData, "PNG", margin, margin - offset, contentWidth, imgHeight);
      remaining -= usableHeight;
    }

    const stamp = new Date().toISOString().slice(0, 10);
    const base = sanitizeFilenamePart(options.workspaceName);
    pdf.save(`${base}-overview-${stamp}.pdf`);
  } finally {
    if (details) {
      details.open = hadOpen;
    }
  }
}
