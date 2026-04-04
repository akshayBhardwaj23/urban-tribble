import NextAuth from "next-auth/next";
import { authOptions } from "@/lib/auth";

// next-auth AuthOptions typing is strict vs our callbacks; runtime shape is valid.
const handler = NextAuth(authOptions as never);
export { handler as GET, handler as POST };
