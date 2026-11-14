// QA against a Vite server already running in your Terminal. Browser UI tests
// mock /api and cannot launch Instagram or publish a real comment.
import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'browser-ui.spec.ts',reporter:[['list'],['html',{open:'never'}]],use:{baseURL:'http://localhost:5173',channel:'chrome',screenshot:'on',trace:'retain-on-failure'}});
