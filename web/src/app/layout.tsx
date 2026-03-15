import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Video2Site",
  description: "Upload a screencast video and get a plan with screenshots",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
