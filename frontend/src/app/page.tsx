import { redirect } from "next/navigation";

// Root path is always either /login or /generate (proxy handles both).
// Redirect to /generate; if the user lacks the cookie, the proxy bounces
// them to /login.
export default function Home() {
  redirect("/generate");
}
