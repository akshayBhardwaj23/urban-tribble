"use client";

import { useSession } from "next-auth/react";
import { HelpPageContent } from "@/components/marketing/help-page-content";

export function HelpPageWithAuth() {
  const { status } = useSession();
  return <HelpPageContent inApp={status === "authenticated"} />;
}
