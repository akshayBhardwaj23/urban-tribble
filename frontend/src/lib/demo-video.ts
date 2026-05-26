export type DemoVideoInfo = {
  provider: "youtube" | "vimeo";
  embedUrl: string;
  watchUrl: string;
};

function parseYoutubeId(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  try {
    const url = new URL(trimmed);
    const host = url.hostname.replace(/^www\./, "");

    if (host === "youtu.be") {
      const id = url.pathname.split("/").filter(Boolean)[0];
      return id && /^[\w-]{11}$/.test(id) ? id : null;
    }

    if (host === "youtube.com" || host === "m.youtube.com") {
      const v = url.searchParams.get("v");
      if (v && /^[\w-]{11}$/.test(v)) return v;
      const parts = url.pathname.split("/").filter(Boolean);
      const embedIdx = parts.indexOf("embed");
      if (embedIdx >= 0 && parts[embedIdx + 1]) {
        const id = parts[embedIdx + 1];
        return /^[\w-]{11}$/.test(id) ? id : null;
      }
      const shortsIdx = parts.indexOf("shorts");
      if (shortsIdx >= 0 && parts[shortsIdx + 1]) {
        const id = parts[shortsIdx + 1];
        return /^[\w-]{11}$/.test(id) ? id : null;
      }
    }
  } catch {
    if (/^[\w-]{11}$/.test(trimmed)) return trimmed;
  }

  return null;
}

function parseVimeoId(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  try {
    const url = new URL(trimmed);
    const host = url.hostname.replace(/^www\./, "");
    if (host !== "vimeo.com" && host !== "player.vimeo.com") return null;
    const parts = url.pathname.split("/").filter(Boolean);
    const id = parts.find((p) => /^\d+$/.test(p));
    return id ?? null;
  } catch {
    return /^\d+$/.test(trimmed) ? trimmed : null;
  }
}

/** Resolve demo video from NEXT_PUBLIC_DEMO_VIDEO_URL (YouTube or Vimeo). */
export function getDemoVideoInfo(): DemoVideoInfo | null {
  const raw = process.env.NEXT_PUBLIC_DEMO_VIDEO_URL?.trim();
  if (!raw) return null;

  const youtubeId = parseYoutubeId(raw);
  if (youtubeId) {
    return {
      provider: "youtube",
      embedUrl: `https://www.youtube-nocookie.com/embed/${youtubeId}?rel=0&modestbranding=1`,
      watchUrl: `https://www.youtube.com/watch?v=${youtubeId}`,
    };
  }

  const vimeoId = parseVimeoId(raw);
  if (vimeoId) {
    return {
      provider: "vimeo",
      embedUrl: `https://player.vimeo.com/video/${vimeoId}?dnt=1`,
      watchUrl: `https://vimeo.com/${vimeoId}`,
    };
  }

  return null;
}
