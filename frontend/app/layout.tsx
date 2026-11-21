import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = { title: 'Personal RAG Assistant', description: 'Ask your documents. Get answers you can verify.' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
