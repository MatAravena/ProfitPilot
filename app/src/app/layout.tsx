import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "next-themes";
import { Navbar } from "@components/Navbar";
import { Footer } from "@components/Footer";
import StoreProvider from "@store/StoreProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Profit Pilot",
  description: "Improving economical situation for everyone",
  applicationName: "Profit Pilot",
  authors: [{name:"Matias Aravena"}]
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
      <html lang="en" suppressHydrationWarning>
        <head >
          {/* <link rel="icon" href="/images/logos/logo-color.png" type="image/png" sizes="32x32" /> */}
        </head>
        <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
          <ThemeProvider attribute="class">
            <StoreProvider>
              <Navbar />
              <div>{children}</div>
            </StoreProvider>
            <Footer />
            {/* component with contact messages */}
            {/* <PopupWidget /> */}
          </ThemeProvider>
        </body>
      </html>
  );
}

{/* <html lang="en">
  <body
    className={`${geistSans.variable} ${geistMono.variable} antialiased`}
  >
    <header className="bg-slate-900 text-white p-4 text-center">
      <p>Welcome to profit pilot</p>
      <Navigation />
    </header>
      {children}
    <footer className="bg-slate-900 text-white p-4 text-center">
      Profit Pilot
    </footer>
  </body>
</html> */}
