import type { Metadata } from "next";
import { Figtree, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AppBar } from "@/components/AppBar";
import { NAME } from "@/shared/brand";

const sans = Figtree({ subsets: ["latin"], variable: "--font-sans", weight: ["400", "500", "600", "700", "800"] });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400", "500"] });

export const metadata: Metadata = {
  title: { default: NAME, template: `%s · ${NAME}` },
  description:
    "What happened to power projects waiting to join California's grid, and how likely a new one is to be built at each substation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <AppBar />
        <main>{children}</main>
      </body>
    </html>
  );
}
