#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import https from 'node:https';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

const API_URL = process.env.PO_MINDMAP_API_URL || 'https://smart.processon.com/v1/api/transform/md';
const ALLOWED = new Set([
  'mind_free', 'mind_right', 'mind_org', 'mind_ishikawa_left',
  'mind_timeline_h', 'mind_tree_free', 'mind_treeTable_left_title',
]);

function parseArgs(argv) {
  const out = { mode: 'general', structure: 'mind_free', markdown: null, title: null, themeJson: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--mode') out.mode = argv[++i];
    else if (a === '--title') out.title = argv[++i];
    else if (a === '--structure') out.structure = argv[++i];
    else if (a === '--markdown') out.markdown = argv[++i];
    else if (a === '--theme-json') out.themeJson = argv[++i];
    else if (a === '--help' || a === '-h') out.help = true;
    else throw new Error(`unknown_argument:${a}`);
  }
  return out;
}

async function readStdin() {
  let s = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) s += chunk;
  return s;
}

function partnerFile() {
  return path.join(os.homedir(), '.processon-unified', 'mindmap-partners.json');
}

function loadPartners() {
  try { return JSON.parse(fs.readFileSync(partnerFile(), 'utf8')); } catch { return {}; }
}

function savePartners(v) {
  fs.mkdirSync(path.dirname(partnerFile()), { recursive: true, mode: 0o700 });
  fs.writeFileSync(partnerFile(), JSON.stringify(v, null, 2) + '\n', { mode: 0o600 });
}

function getPartner(mode) {
  const key = mode === 'document' ? 'document' : 'general';
  const prefix = key === 'document' ? 'skill_mind_doc_' : 'skill_mind_official_';
  const p = loadPartners();
  if (typeof p[key] === 'string' && p[key].startsWith(prefix)) return p[key];
  p[key] = `${prefix}${crypto.randomUUID()}`;
  savePartners(p);
  return p[key];
}

function postJson(url, payload) {
  const u = new URL(url);
  const client = u.protocol === 'https:' ? https : http;
  const body = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const req = client.request(u, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', c => text += c);
      res.on('end', () => {
        if ((res.statusCode || 0) >= 400) {
          reject(new Error(`http_${res.statusCode}:${text.slice(0, 1000)}`));
          return;
        }
        try { resolve(JSON.parse(text)); }
        catch { reject(new Error(`invalid_json:${text.slice(0, 1000)}`)); }
      });
    });
    req.on('error', reject);
    req.setTimeout(120000, () => req.destroy(new Error('request_timeout')));
    req.end(body);
  });
}

function enrich(result) {
  const d = result?.data;
  if (!d || typeof d !== 'object') return result;
  if (typeof d.imgUrl === 'string') d.rawImgUrl = d.imgUrl;
  if (typeof d.visitUrl === 'string') d.rawVisitUrl = d.visitUrl;
  return result;
}

async function main() {
  let args;
  try { args = parseArgs(process.argv.slice(2)); }
  catch (e) { console.error(`ERROR:${e.message}`); return 1; }

  if (args.help) {
    console.log('Usage: node processon-mindmap.mjs --mode general|document --title <title> --structure <structure> --markdown <text|-> [--theme-json <json>]');
    return 0;
  }
  if (!args.title) { console.error('ERROR:title_required'); return 1; }
  if (args.markdown == null) { console.error('ERROR:markdown_required'); return 1; }
  if (!['general', 'document'].includes(args.mode)) { console.error('ERROR:invalid_mode'); return 1; }

  const markdown = args.markdown === '-' ? await readStdin() : args.markdown;
  const structure = ALLOWED.has(args.structure) ? args.structure : 'mind_free';
  const payload = {
    title: args.title,
    markdown,
    structure,
    source: args.mode === 'document' ? 'skill_all_mind_documentsummary' : 'skill_all_mind_official',
    partnerFlag: getPartner(args.mode),
  };
  if (args.themeJson) {
    try { payload.theme = JSON.parse(args.themeJson); }
    catch { console.error('ERROR:invalid_theme_json'); return 1; }
  }

  try {
    const result = enrich(await postJson(API_URL, payload));
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    return result?.success === false ? 1 : 0;
  } catch (e) {
    process.stdout.write(JSON.stringify({ success: false, error: e.message }, null, 2) + '\n');
    return 1;
  }
}

process.exitCode = await main();
