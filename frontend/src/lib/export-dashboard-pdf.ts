import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

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
      onclone: (clonedDoc) => {
        clonedDoc.documentElement.classList.remove("dark");
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
