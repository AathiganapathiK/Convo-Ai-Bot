import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  esbuild: {
    loader: 'jsx',
    include: /src\/.*\.jsx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
  define: {
    'process.env.REACT_APP_API_BASE_URL': JSON.stringify(process.env.REACT_APP_API_BASE_URL || ''),
  },
  server: {
    port: 3000,
    open: false,
    proxy: {
      '/ask': 'http://127.0.0.1:8000',
      '/chat-sessions': 'http://127.0.0.1:8000',
      '/users': 'http://127.0.0.1:8000',
      '/roles': 'http://127.0.0.1:8000',
      '/user-roles': 'http://127.0.0.1:8000',
      '/providers': 'http://127.0.0.1:8000',
      '/connections': 'http://127.0.0.1:8000',
      '/semantic': 'http://127.0.0.1:8000',
      '/rbac': 'http://127.0.0.1:8000',
      '/schema': 'http://127.0.0.1:8000',
      '/intents': 'http://127.0.0.1:8000',
      '/pipeline': 'http://127.0.0.1:8000',
      '/audit': 'http://127.0.0.1:8000',
      '/export': 'http://127.0.0.1:8000',
      '/config': 'http://127.0.0.1:8000',
      '/auth': 'http://127.0.0.1:8000',
    },
  },
});
