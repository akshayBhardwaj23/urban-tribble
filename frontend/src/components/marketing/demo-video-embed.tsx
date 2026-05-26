import { getDemoVideoInfo } from "@/lib/demo-video";
import { cn } from "@/lib/utils";

type DemoVideoEmbedProps = {
  title?: string;
  className?: string;
};

export function DemoVideoEmbed({
  title = "Snaptix product demo",
  className,
}: DemoVideoEmbedProps) {
  const video = getDemoVideoInfo();

  if (!video) {
    return (
      <div
        className={cn(
          "flex aspect-video w-full flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50/80 px-6 text-center dark:border-slate-700 dark:bg-slate-900/40",
          className
        )}
      >
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
          Demo video coming soon
        </p>
        <p className="mt-2 max-w-md text-xs leading-relaxed text-muted-foreground">
          Set{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
            NEXT_PUBLIC_DEMO_VIDEO_URL
          </code>{" "}
          to your YouTube or Vimeo link, then redeploy the frontend.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="relative aspect-video w-full overflow-hidden rounded-2xl border border-slate-200/90 bg-black shadow-sm dark:border-white/10">
        <iframe
          src={video.embedUrl}
          title={title}
          className="absolute inset-0 h-full w-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Prefer to open in a new tab?{" "}
        <a
          href={video.watchUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-foreground underline underline-offset-2"
        >
          Watch on {video.provider === "youtube" ? "YouTube" : "Vimeo"}
        </a>
      </p>
    </div>
  );
}
