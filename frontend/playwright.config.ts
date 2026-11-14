import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',reporter:[['list'],['html',{open:'never'}]],use:{baseURL:'http://localhost:5175',channel:'chrome',screenshot:'on',trace:'retain-on-failure'},webServer:[
 {command:'MODE=demo DATABASE_URL=sqlite:///./e2e-demo.db FRONTEND_ORIGIN=http://localhost:5175 ../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --port 8005 --no-access-log',port:8005,reuseExistingServer:false},
 {command:'API_PROXY_TARGET=http://127.0.0.1:8005 npm run dev -- --port 5175 --strictPort',port:5175,reuseExistingServer:false}
]});
