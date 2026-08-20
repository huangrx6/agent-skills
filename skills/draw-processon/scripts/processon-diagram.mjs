#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import https from 'node:https';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

const cfg = {
  apiBase: process.env.PO_API_BASE_URL || 'https://smart.processon.com',
  authBase: process.env.PO_AUTH_BASE_URL || 'https://smart.processon.com/auth',
  tokenQueryPath: process.env.PO_TOKEN_QUERY_PATH || '/v1/token/temporary/query',
  mcpUrl: process.env.PO_MCP_URL || 'https://smart.processon.com/mcp',
  authPsk: process.env.PO_AUTH_PSK || 'processon_mcp_psk_2026',
};

const stateDir = path.join(os.tmpdir(), `processon-unified-${typeof process.getuid === 'function' ? process.getuid() : (process.env.USERNAME || process.env.USER || 'user')}`);
const codeFile = path.join(stateDir, 'current-code');
const tokenDir = path.join(os.homedir(), '.processon-unified');
const tokenFile = path.join(tokenDir, 'diagram-token.json');

function status(s) { process.stdout.write(`${s}\n`); }
function ensureDir(p) { fs.mkdirSync(p, { recursive: true, mode: 0o700 }); }
function clearCode() { try { fs.rmSync(codeFile, { force: true }); } catch {} }
function clearToken() { try { fs.rmSync(tokenFile, { force: true }); } catch {} }

function normalizeAuth(v) {
  if (!v) return '';
  return String(v).startsWith('Bearer ') ? String(v) : `Bearer ${v}`;
}

function readToken() {
  try {
    const data = JSON.parse(fs.readFileSync(tokenFile, 'utf8'));
    return normalizeAuth(data.authorization || data.token || '');
  } catch { return ''; }
}

function saveToken(token) {
  const authorization = normalizeAuth(token);
  if (!authorization) return false;
  ensureDir(tokenDir);
  fs.writeFileSync(tokenFile, JSON.stringify({ authorization, mcpUrl: cfg.mcpUrl, updatedAt: Date.now() }, null, 2) + '\n', { mode: 0o600 });
  return true;
}

function makeCode() {
  const randomId = crypto.randomBytes(8).toString('hex');
  const ts = Math.floor(Date.now() / 1000);
  const payload = `po_mcp_${randomId}_${ts}`;
  const md5Hex = crypto.createHash('md5').update(cfg.authPsk).digest('hex');
  const ivHex = md5Hex.split('').reverse().join('');
  const cipher = crypto.createCipheriv('aes-128-cbc', Buffer.from(md5Hex, 'hex'), Buffer.from(ivHex, 'hex'));
  const enc = Buffer.concat([cipher.update(payload, 'utf8'), cipher.final()]).toString('base64');
  return enc.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function startAuth() {
  ensureDir(stateDir);
  const code = makeCode();
  fs.writeFileSync(codeFile, `${code}\n`, { mode: 0o600 });
  status(`AUTH_REQUIRED:${cfg.authBase}?code=${encodeURIComponent(code)}&origin=skill`);
}

function readCode() {
  try { return fs.readFileSync(codeFile, 'utf8').trim(); } catch { return ''; }
}

function requestJson(url, options = {}, body = null) {
  const u = new URL(url);
  const client = u.protocol === 'https:' ? https : http;
  return new Promise((resolve, reject) => {
    const req = client.request(u, options, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', c => text += c);
      res.on('end', () => {
        if ((res.statusCode || 0) >= 400) {
          const err = new Error(`http_${res.statusCode}:${text.slice(0, 1000)}`);
          err.statusCode = res.statusCode;
          reject(err);
          return;
        }
        try { resolve(JSON.parse(text)); }
        catch {
          const dataLines = text.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).filter(Boolean);
          if (dataLines.length) {
            try { resolve(JSON.parse(dataLines.join('\n'))); return; } catch {}
          }
          reject(new Error(`invalid_json:${text.slice(0, 1000)}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(60000, () => req.destroy(new Error('request_timeout')));
    if (body != null) req.write(body);
    req.end();
  });
}

async function queryToken() {
  const code = readCode();
  if (!code) return { kind: 'error', message: 'no_code' };
  const u = new URL(cfg.tokenQueryPath, cfg.apiBase);
  u.searchParams.set('code', code);
  try {
    const payload = await requestJson(u.toString(), { method: 'GET' });
    const token = payload?.data?.token || '';
    if (token) return { kind: 'token', token };
    const c = String(payload?.code || '');
    if (c === '401' || c === '403') return { kind: 'error', message: 'invalid_code' };
    return { kind: 'pending', payload };
  } catch (e) {
    return { kind: 'error', message: `network:${e.message}` };
  }
}

async function fetchToken({ pendingIsOkay = false } = {}) {
  const r = await queryToken();
  if (r.kind === 'token') {
    saveToken(r.token);
    clearCode();
    status('TOKEN_READY');
    return 0;
  }
  if (r.kind === 'pending' && pendingIsOkay) {
    status('TOKEN_PENDING');
    return 0;
  }
  if (r.kind === 'pending') {
    status('ERROR:token_pending');
    return 1;
  }
  status(`ERROR:${r.message}`);
  return 1;
}

function extractContent(payload) {
  const content = payload?.result?.content;
  if (!Array.isArray(content)) return payload;
  const text = content.filter(x => x?.type === 'text' && x.text).map(x => x.text).join('\n').trim();
  if (!text) return payload;
  try { return JSON.parse(text); } catch { return { content: text }; }
}

async function generate(prompt) {
  const authorization = readToken();
  if (!authorization) {
    status('AUTH_REQUIRED_LOCAL');
    return 2;
  }
  const body = JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: { name: 'generate_chart', arguments: { prompt } },
  });
  try {
    const payload = await requestJson(cfg.mcpUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'Content-Length': Buffer.byteLength(body),
        'Authorization': authorization,
      },
    }, body);
    const text = JSON.stringify(payload);
    if (/token_expired|unauthorized|forbidden/i.test(text)) {
      clearToken();
      status('AUTH_EXPIRED');
      return 3;
    }
    process.stdout.write(JSON.stringify(extractContent(payload), null, 2) + '\n');
    return payload?.error ? 1 : 0;
  } catch (e) {
    if (e.statusCode === 401 || e.statusCode === 403 || /token_expired|unauthorized|forbidden/i.test(e.message || '')) {
      clearToken();
      status('AUTH_EXPIRED');
      return 3;
    }
    status(`ERROR:mcp:${e.message}`);
    return 1;
  }
}

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  switch (command) {
    case 'check':
      if (readToken()) status('READY'); else startAuth();
      return 0;
    case 'poll':
      return fetchToken({ pendingIsOkay: true });
    case 'fetch':
      return fetchToken({ pendingIsOkay: false });
    case 'reauth':
      clearToken(); clearCode(); startAuth(); return 0;
    case 'generate': {
      const prompt = rest.join(' ').trim();
      if (!prompt) { status('ERROR:no_prompt'); return 1; }
      return generate(prompt);
    }
    default:
      status('Usage: node processon-diagram.mjs [check|poll|fetch|reauth|generate <prompt>]');
      return 1;
  }
}

process.exitCode = await main();
