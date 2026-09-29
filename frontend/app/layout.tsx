import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Thanisha, It’s Done Bro",
  description: "A fictional election-office snake ballot for a date invitation.",
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
