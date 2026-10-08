import type { Metadata } from "next";
import "./globals.css";
import "./futuristic.css";
export const metadata: Metadata = {
  title: "One Question · A message from Spandan",
  description: "A private date invitation from Spandan.",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
