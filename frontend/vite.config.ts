import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[react(),tailwindcss()],server:{watch:{ignored:['**/.pnpm-store/**','**/test-results/**','**/dist/**','**/*.tsbuildinfo']},proxy:{'/api':{target:process.env.API_PROXY_TARGET||'http://127.0.0.1:8000',changeOrigin:true}}},build:{rollupOptions:{output:{manualChunks:{charts:['recharts'],react:['react','react-dom','react-router-dom'],query:['@tanstack/react-query','axios']}}}},test:{environment:'jsdom',setupFiles:['./src/test-setup.ts'],include:['src/**/*.test.tsx']}});
