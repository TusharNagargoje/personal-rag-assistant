import type { Config } from 'tailwindcss';
const config: Config = { content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'], theme: { extend: { colors: { ink: '#14231f', forest: '#174d3b', lime: '#d4f17a', canvas: '#f6f7f2' } } }, plugins: [] };
export default config;
