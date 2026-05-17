import Image from "next/image";
import Link from "next/link";
import { LOGO_SRC, PRODUCT_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

type BrandLogoProps = {
  href?: string;
  showName?: boolean;
  className?: string;
  nameClassName?: string;
  iconClassName?: string;
};

export function BrandLogo({
  href = "/",
  showName = true,
  className,
  nameClassName,
  iconClassName,
}: BrandLogoProps) {
  const content = (
    <>
      <Image
        src={LOGO_SRC}
        alt={showName ? "" : `${PRODUCT_NAME} logo`}
        width={602}
        height={972}
        className={cn(
          "h-9 w-auto shrink-0 object-contain dark:invert",
          iconClassName,
        )}
        priority
        aria-hidden={showName}
      />
      {showName ? (
        <span
          className={cn(
            "font-semibold tracking-tight text-slate-900 dark:text-white",
            nameClassName,
          )}
        >
          {PRODUCT_NAME}
        </span>
      ) : null}
    </>
  );

  const rootClass = cn("inline-flex min-w-0 items-center gap-2.5", className);

  if (href) {
    return (
      <Link href={href} className={rootClass} aria-label={PRODUCT_NAME}>
        {content}
      </Link>
    );
  }

  return <div className={rootClass}>{content}</div>;
}
