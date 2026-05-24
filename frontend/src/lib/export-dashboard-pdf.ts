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

/** html2canvas cannot parse lab/oklch/color-mix in stylesheet rules. */
const MODERN_COLOR_FN = /(lab|oklch|lch|color-mix|color)\(/i;

/**
 * html2canvas cannot parse modern CSS color serializations from stylesheets.
 * Canvas fillStyle accepts them and re-serializes to #hex/rgb.
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
  if (MODERN_COLOR_FN.test(t)) {
    const ctx = getCanvas2d();
    if (!ctx) return null;
    try {
      ctx.fillStyle = "#000000";
      ctx.fillStyle = t;
      const out = String(ctx.fillStyle);
      if (out.startsWith("#") || out.startsWith("rgb")) {
        return out;
      }
    } catch {
      return null;
    }
    return null;
  }
  if (t.startsWith("#") || t.startsWith("rgb")) {
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
    return null;
  }
  return t;
}

const COLOR_PROPS = new Set([
  "color",
  "background-color",
  "border-top-color",
  "border-right-color",
  "border-bottom-color",
  "border-left-color",
  "outline-color",
  "text-decoration-color",
  "column-rule-color",
  "fill",
  "stroke",
  "stop-color",
  "flood-color",
  "lighting-color",
]);

/** Layout + typography mirrored as inline styles after stylesheets are stripped. */
const MIRROR_PROPS = [
  "display",
  "position",
  "box-sizing",
  "top",
  "right",
  "bottom",
  "left",
  "width",
  "height",
  "min-width",
  "max-width",
  "min-height",
  "max-height",
  "margin-top",
  "margin-right",
  "margin-bottom",
  "margin-left",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "flex",
  "flex-direction",
  "flex-wrap",
  "flex-grow",
  "flex-shrink",
  "flex-basis",
  "align-items",
  "align-self",
  "justify-content",
  "gap",
  "row-gap",
  "column-gap",
  "grid-template-columns",
  "grid-template-rows",
  "grid-column",
  "grid-row",
  "font-size",
  "font-weight",
  "font-family",
  "line-height",
  "letter-spacing",
  "text-align",
  "text-transform",
  "white-space",
  "word-break",
  "border-top-width",
  "border-right-width",
  "border-bottom-width",
  "border-left-width",
  "border-top-style",
  "border-right-style",
  "border-bottom-style",
  "border-left-style",
  "border-top-color",
  "border-right-color",
  "border-bottom-color",
  "border-left-color",
  "border-radius",
  "background-color",
  "color",
  "opacity",
  "overflow",
  "overflow-x",
  "overflow-y",
  "z-index",
  "vertical-align",
  "list-style-type",
  "object-fit",
];

function stripStylesheets(doc: Document): void {
  doc.querySelectorAll('style, link[rel="stylesheet"]').forEach((node) => {
    node.remove();
  });
}

function safeStyleValue(prop: string, raw: string): string | null {
  const t = raw.trim();
  if (!t) return null;

  if (prop === "background-image") {
    if (MODERN_COLOR_FN.test(t)) return "none";
    return t;
  }

  if (prop === "box-shadow" || prop === "text-shadow") {
    if (MODERN_COLOR_FN.test(t)) return "none";
    return t;
  }

  if (COLOR_PROPS.has(prop) || prop === "fill" || prop === "stroke") {
    return toCanvasSafeColor(t) ?? (MODERN_COLOR_FN.test(t) ? null : t);
  }

  if (MODERN_COLOR_FN.test(t)) {
    return null;
  }

  return t;
}

function mirrorSvgPaint(orig: Element, copy: Element): void {
  if (orig.namespaceURI !== "http://www.w3.org/2000/svg") {
    return;
  }
  const cs = getComputedStyle(orig);
  const fill = toCanvasSafeColor(cs.fill);
  const stroke = toCanvasSafeColor(cs.stroke);
  if (fill && fill !== "none") {
    copy.setAttribute("fill", fill);
  }
  if (stroke && stroke !== "none") {
    copy.setAttribute("stroke", stroke);
  }
}

/**
 * Copy resolved computed styles onto the clone as inline rgb/hex so layout survives
 * after stylesheets are removed and html2canvas never sees lab/oklch rules.
 */
function mirrorCloneStylesFromOriginal(
  originalRoot: Element,
  cloneRoot: Element
): void {
  const origEls: Element[] = [originalRoot, ...originalRoot.querySelectorAll("*")];
  const cloneEls: Element[] = [cloneRoot, ...cloneRoot.querySelectorAll("*")];
  const n = Math.min(origEls.length, cloneEls.length);

  for (let i = 0; i < n; i += 1) {
    const orig = origEls[i];
    const copy = cloneEls[i] as HTMLElement;
    if (!copy?.style || !orig.ownerDocument) continue;

    const cs = getComputedStyle(orig);

    for (const prop of MIRROR_PROPS) {
      const raw = cs.getPropertyValue(prop);
      const safe = safeStyleValue(prop, raw);
      if (safe) {
        copy.style.setProperty(prop, safe, "important");
      }
    }

    const bgImage = cs.getPropertyValue("background-image");
    if (bgImage && bgImage !== "none") {
      const safeBg = safeStyleValue("background-image", bgImage);
      copy.style.setProperty(
        "background-image",
        safeBg ?? "none",
        "important"
      );
    }

    for (const shadowProp of ["box-shadow", "text-shadow"] as const) {
      const raw = cs.getPropertyValue(shadowProp);
      if (!raw || raw === "none") continue;
      const safe = safeStyleValue(shadowProp, raw);
      copy.style.setProperty(shadowProp, safe ?? "none", "important");
    }

    mirrorSvgPaint(orig, copy);

    const inlineStyle = copy.getAttribute("style");
    if (inlineStyle && MODERN_COLOR_FN.test(inlineStyle)) {
      for (const part of inlineStyle.split(";")) {
        const idx = part.indexOf(":");
        if (idx < 0) continue;
        const key = part.slice(0, idx).trim();
        const val = part.slice(idx + 1).trim();
        if (!key || !MODERN_COLOR_FN.test(val)) continue;
        const safe = safeStyleValue(key, val);
        if (safe) {
          copy.style.setProperty(key, safe, "important");
        } else {
          copy.style.removeProperty(key);
        }
      }
    }

    for (const attr of ["fill", "stroke"] as const) {
      const attrVal = copy.getAttribute(attr);
      if (
        attrVal &&
        (attrVal.includes("var(") || MODERN_COLOR_FN.test(attrVal))
      ) {
        const safe = toCanvasSafeColor(cs.getPropertyValue(attr));
        if (safe) {
          copy.setAttribute(attr, safe);
        } else {
          copy.removeAttribute(attr);
        }
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
        clonedDoc.body.style.background = "#ffffff";
        clonedDoc.body.style.color = "#0f172a";

        clonedDoc.querySelectorAll("[data-pdf-exclude]").forEach((el) => {
          el.remove();
        });

        const cloneRoot =
          clonedElement ??
          (clonedDoc.querySelector(".dashboard-pdf-root") as HTMLElement | null);

        if (cloneRoot) {
          mirrorCloneStylesFromOriginal(root, cloneRoot);
          cloneRoot.style.setProperty("background", "#ffffff", "important");
          cloneRoot.style.setProperty("color", "#0f172a", "important");
        }

        stripStylesheets(clonedDoc);
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
