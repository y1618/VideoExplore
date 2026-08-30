import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VideoExplore",
  description: "動画セマンティック検索 — テキストで探して、すぐ再生",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-neutral-950 text-neutral-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
