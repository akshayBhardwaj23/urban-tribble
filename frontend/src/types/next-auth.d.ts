import type { DefaultSession } from "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    /** Signed FastAPI access token; send as Authorization: Bearer. */
    accessToken?: string;
    /** Set when the API token could not be renewed — the user must sign in again. */
    error?: "SessionExpired";
    user: {
      email: string;
      name?: string | null;
      image?: string | null;
    } & DefaultSession["user"];
  }

  interface User {
    accessToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    /** Epoch ms at which `accessToken` expires; drives server-side renewal. */
    accessTokenExpires?: number;
    error?: "SessionExpired";
  }
}
