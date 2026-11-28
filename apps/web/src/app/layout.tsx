import type { Metadata } from "next";
import { Providers } from "./providers";
import "./globals.css";
import "@xyflow/react/dist/style.css";

export const metadata: Metadata = {
  title: "Miro - AI Operating Workspace",
  description:
    "Command. Execute. Observe. Control. Personal AI Operating Workspace combining natural-language collaboration, direct tool operation, and autonomous workflows.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased" suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
