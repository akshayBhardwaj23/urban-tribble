"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type ChartFrameProps = {
  className?: string;
  minHeight?: number;
  children: React.ReactNode;
};

export function ChartFrame({
  className,
  minHeight = 304,
  children,
}: ChartFrameProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const update = () => {
      const rect = node.getBoundingClientRect();
      setIsReady(rect.width > 0 && rect.height > 0);
    };

    update();

    const observer = new ResizeObserver(() => update());
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      className={cn("h-full w-full min-w-0", className)}
      style={{ minHeight }}
    >
      {isReady ? children : null}
    </div>
  );
}
