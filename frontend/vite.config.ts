import { defineConfig, type Plugin } from 'vite';
import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const apiPort = Number(process.env.WORLDS_API_PORT || 8026);
const webPort = Number(process.env.WORLDS_WEB_PORT || 5173);
if (![apiPort, webPort].every(port => Number.isInteger(port) && port >= 1024 && port <= 65535)) throw new Error('Invalid local service port');
const instanceId = createHash('sha256').update(realpathSync(fileURLToPath(new URL('..', import.meta.url)))).digest('hex');
const identity: Plugin = {
  name: 'local-checkout-identity',
  configureServer(server) { server.middlewares.use('/__worlds_instance', (_req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ instance_id: instanceId, api_port: apiPort })); }); },
  configurePreviewServer(server) { server.middlewares.use('/__worlds_instance', (_req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ instance_id: instanceId, api_port: apiPort })); }); },
};
const proxy = {
  '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, '') },
};

export default defineConfig({
  plugins: [identity, react(), tailwindcss()],
  server: { host: '127.0.0.1', port: webPort, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: webPort, strictPort: true, proxy },
});
