import {defineConfig} from '@playwright/test';
const url=process.env.E2E_BASE_URL||'http://127.0.0.1:5173';
export default defineConfig({testDir:'./tests',timeout:60000,use:{baseURL:url,trace:'retain-on-failure'},webServer:{command:'node node_modules/vite/bin/vite.js --host 127.0.0.1',url,reuseExistingServer:!process.env.CI}});
