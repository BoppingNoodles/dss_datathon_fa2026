import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

const themeScript = `try{var q=new URLSearchParams(location.search).get('theme');var t=(q==='light'||q==='dark')?q:localStorage.getItem('phoenix-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}`;

export const metadata: Metadata = {
  title: "Phoenix",
  description: "Find jobs, neighborhood rent ranges, and community services in the East Bay.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        {/* Apply a saved light/dark choice before first paint so the page doesn't flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
