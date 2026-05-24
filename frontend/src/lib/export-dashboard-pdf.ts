import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

const PDF_EXPORT_CLASS = "pdf-export-active";

/** html2canvas 1.x cannot parse these in stylesheet rules. */
const MODERN_COLOR_FN = /oklch\(|lab\(|lch\(|color-mix\(/i;

const PDF_SAFE_THEME = `
:root, .dark, html {
  color-scheme: light !important;
  --background: #ffffff !important;
  --foreground: #0f172a !important;
  --card: #ffffff !important;
  --card-foreground: #0f172a !important;
  --popover: #ffffff !important;
  --popover-foreground: #0f172a !important;
  --primary: #1e293b !important;
  --primary-foreground: #f8fafc !important;
  --secondary: #f1f5f9 !important;
  --secondary-foreground: #0f172a !important;
  --muted: #f1f5f9 !important;
  --muted-foreground: #64748b !important;
  --accent: #f1f5f9 !important;
  --accent-foreground: #0f172a !important;
  --destructive: #dc2626 !important;
  --border: #e2e8f0 !important;
  --input: #e2e8f0 !important;
  --ring: #94a3b8 !important;
  --chart-1: #94a3b8 !important;
  --chart-2: #475569 !important;
  --chart-3: #64748b !important;
  --chart-4: #78716c !important;
  --chart-5: #57534e !important;
  --pie-1: #b45309 !important;
  --pie-2: #c2410c !important;
  --pie-3: #4d7c0f !important;
  --pie-4: #7e22ce !important;
  --pie-5: #a16207 !important;
  --pie-6: #9a3412 !important;
  --pie-7: #0369a1 !important;
  --pie-8: #ca8a04 !important;
}
body {
  background: #ffffff !important;
  color: #0f172a !important;
}
`;

function sanitizeCssText(css: string): string {
  let out = css;
  const patterns = [
    /oklch\((?:[^()"]|\([^()]*\))*\)/gi,
    /lab\((?:[^()"]|\([^()]*\))*\)/gi,
    /lch\((?:[^()"]|\([^()]*\))*\)/gi,
    /color-mix\([^;{}]+\)/gi,
  ];
  for (const re of patterns) {
    out = out.replace(re, "#64748b");
  }
  return out;
}

function rewriteStylesheetsInClone(doc: Document): void {
  doc.querySelectorAll("style").forEach((node) => {
    const text = node.textContent;
    if (text && MODERN_COLOR_FN.test(text)) {
      node.textContent = sanitizeCssText(text);
    }
  });
}

function injectPdfTheme(doc: Document): void {
  const el = doc.createElement("style");
  el.setAttribute("data-pdf-theme", "true");
  el.textContent = PDF_SAFE_THEME;
  doc.head.appendChild(el);
}

function prepareClonedDocument(doc: Document): void {
  doc.documentElement.classList.remove("dark");
  rewriteStylesheetsInClone(doc);
  injectPdfTheme(doc);
  doc.body.style.background = "#ffffff";
  doc.body.style.color = "#0f172a";
  doc.querySelectorAll("[data-pdf-exclude]").forEach((node) => node.remove());
}

function collectPdfBlocks(root: HTMLElement): HTMLElement[] {
  const blocks: HTMLElement[] = [];
  for (const child of Array.from(root.children)) {
    if (!(child instanceof HTMLElement)) continue;
    if (child.hasAttribute("data-pdf-exclude")) continue;
    const h = Math.max(child.offsetHeight, child.scrollHeight);
    if (h < 8) continue;
    blocks.push(child);
  }
  return blocks.length > 0 ? blocks : [root];
}

async function waitForCharts(): Promise<void> {
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
  await new Promise<void>((resolve) => {
    setTimeout(resolve, 400);
  });
}

async function captureElement(el: HTMLElement): Promise<HTMLCanvasElement> {
  const width = Math.ceil(Math.max(el.scrollWidth, el.clientWidth, 320));
  const height = Math.ceil(Math.max(el.scrollHeight, el.clientHeight, 40));

  return html2canvas(el, {
    scale: Math.min(2, window.devicePixelRatio || 2),
    backgroundColor: "#ffffff",
    useCORS: true,
    logging: false,
    width,
    height,
    windowWidth: width,
    windowHeight: height,
    scrollX: 0,
    scrollY: -window.scrollY,
    onclone: (clonedDoc) => {
      prepareClonedDocument(clonedDoc);
    },
  });
}

function appendCanvasToPdf(
  pdf: jsPDF,
  canvas: HTMLCanvasElement,
  state: { cursorY: number; pageWidth: number; pageHeight: number; margin: number }
): void {
  const contentWidth = state.pageWidth - state.margin * 2;
  const usableHeight = state.pageHeight - state.margin * 2;
  const gap = 14;

  const imgData = canvas.toDataURL("image/png", 0.92);
  const imgHeight = (canvas.height * contentWidth) / canvas.width;

  let offset = 0;
  while (offset < imgHeight - 1) {
    const chunk = Math.min(usableHeight, imgHeight - offset);

    if (state.cursorY + chunk > state.pageHeight - state.margin) {
      pdf.addPage();
      state.cursorY = state.margin;
    }

    pdf.addImage(
      imgData,
      "PNG",
      state.margin,
      state.cursorY - offset,
      contentWidth,
      imgHeight
    );

    offset += chunk;
    if (offset < imgHeight - 1) {
      pdf.addPage();
      state.cursorY = state.margin;
    } else {
      state.cursorY += chunk + gap;
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
 * Rasterizes the overview dashboard to a multi-page A4 PDF (portrait).
 * Captures section-by-section so layout and charts stay intact.
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

  const html = document.documentElement;
  html.classList.add(PDF_EXPORT_CLASS);
  window.scrollTo(0, 0);

  await waitForCharts();

  try {
    const pdf = new jsPDF({
      orientation: "portrait",
      unit: "pt",
      format: "a4",
    });

    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 40;
    const state = { cursorY: margin, pageWidth, pageHeight, margin };

    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(16);
    pdf.setTextColor(15, 23, 42);
    pdf.text(options.workspaceName, margin, state.cursorY);
    state.cursorY += 22;

    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(10);
    pdf.setTextColor(100, 116, 139);
    pdf.text(
      `Overview · ${new Date().toLocaleDateString(undefined, {
        dateStyle: "long",
      })}`,
      margin,
      state.cursorY
    );
    state.cursorY += 28;

    const blocks = collectPdfBlocks(root);
    for (const block of blocks) {
      const canvas = await captureElement(block);
      if (canvas.width < 2 || canvas.height < 2) continue;
      appendCanvasToPdf(pdf, canvas, state);
    }

    const stamp = new Date().toISOString().slice(0, 10);
    const base = sanitizeFilenamePart(options.workspaceName);
    pdf.save(`${base}-overview-${stamp}.pdf`);
  } finally {
    html.classList.remove(PDF_EXPORT_CLASS);
    if (details) {
      details.open = hadOpen;
    }
  }
}
