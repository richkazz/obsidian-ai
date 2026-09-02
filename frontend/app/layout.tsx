import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "katex/dist/katex.min.css";
import { Providers } from "./providers";
import { ThemeToaster } from "@/components/theme-toaster";

// The container image is built before deployment secrets are available.  Keep
// this layout request-dynamic so ENCRYPTION_KEY is read from the running
// frontend container rather than being baked into the image during `next build`.
export const dynamic = "force-dynamic";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Obsidian AI",
  description: "AI Agent Control Plane",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const runtimeEncryptionKey =
    process.env.ENCRYPTION_KEY || process.env.NEXT_PUBLIC_ENCRYPTION_KEY || "";
  const runtimeConfig = JSON.stringify({
    NEXT_PUBLIC_ENCRYPTION_KEY: runtimeEncryptionKey,
  }).replace(/</g, "\\u003c");

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__ENV = ${runtimeConfig};`,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Providers>{children}</Providers>
        <ThemeToaster />
      </body>
    </html>
  );
}
