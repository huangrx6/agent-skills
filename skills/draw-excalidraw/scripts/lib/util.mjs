import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';

export const now = () => Date.now();
export const randomId = (prefix='el') => `${prefix}_${crypto.randomBytes(8).toString('base64url')}`;
export const randomInt = () => crypto.randomInt(1, 2_147_483_000);
export const sha1 = (s) => crypto.createHash('sha1').update(s).digest('hex');
export const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
export const deepClone = (v) => JSON.parse(JSON.stringify(v));

export async function readJson(file) {
  return JSON.parse(await fs.readFile(file, 'utf8'));
}
export async function writeJson(file, value) {
  await fs.mkdir(path.dirname(path.resolve(file)), { recursive: true });
  await fs.writeFile(file, JSON.stringify(value, null, 2) + '\n', 'utf8');
}
export async function ensureDir(dir) { await fs.mkdir(dir, { recursive: true }); }
export const exists = async (p) => !!(await fs.stat(p).catch(() => null));
export const slug = (s='') => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9\u4e00-\u9fff]+/g,'-').replace(/^-|-$/g,'') || 'diagram';

export function charUnits(s='') {
  let units = 0;
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (/\s/.test(ch)) units += 0.35;
    else if (cp >= 0x2e80 || /[\u3040-\u30ff\uac00-\ud7af]/.test(ch)) units += 1.0;
    else if (/[A-ZMW@#%&]/.test(ch)) units += 0.72;
    else if (/[ilI1|.,:;!']/.test(ch)) units += 0.32;
    else units += 0.56;
  }
  return units;
}

export function measureText(text='', fontSize=16, lineHeight=1.25) {
  const lines = String(text).split('\n');
  const width = Math.max(1, ...lines.map(l => charUnits(l) * fontSize));
  const height = Math.max(fontSize * lineHeight, lines.length * fontSize * lineHeight);
  return { width, height, lines: lines.length };
}

export function wrapText(text='', maxUnits=22) {
  const source = String(text).trim();
  if (!source) return '';
  const out=[]; let line=''; let units=0;
  const tokens = source.includes(' ') ? source.split(/(\s+)/) : [...source];
  for (const token of tokens) {
    const u = charUnits(token);
    if (line && units + u > maxUnits) { out.push(line.trim()); line=''; units=0; }
    line += token; units += u;
  }
  if (line.trim()) out.push(line.trim());
  return out.join('\n');
}

export function fuzzyScore(query, value) {
  query = query.toLowerCase().trim(); value = value.toLowerCase();
  if (!query) return 0;
  if (value === query) return 1000;
  if (value.startsWith(query)) return 800 - value.length;
  if (value.includes(query)) return 600 - value.indexOf(query);
  let qi=0, gaps=0;
  for (let i=0;i<value.length && qi<query.length;i++) {
    if (value[i]===query[qi]) qi++; else if(qi>0) gaps++;
  }
  return qi===query.length ? 300-gaps : -1;
}

export function bboxUnion(boxes) {
  if (!boxes.length) return {x:0,y:0,width:0,height:0};
  const minX=Math.min(...boxes.map(b=>b.x)), minY=Math.min(...boxes.map(b=>b.y));
  const maxX=Math.max(...boxes.map(b=>b.x+b.width)), maxY=Math.max(...boxes.map(b=>b.y+b.height));
  return {x:minX,y:minY,width:maxX-minX,height:maxY-minY};
}

export function boxesOverlap(a,b,pad=0) {
  return !(a.x+a.width+pad <= b.x || b.x+b.width+pad <= a.x || a.y+a.height+pad <= b.y || b.y+b.height+pad <= a.y);
}
