import { redirect } from "next/navigation";

/**
 * Legacy URL — the CSC admin view now lives inside the unified app shell
 * at /generate (toggled via sidebar). This redirect keeps any old bookmarks
 * working without ever rendering a duplicate MacShell.
 */
export default function CscAdminLegacyRedirect() {
  redirect("/generate");
}
