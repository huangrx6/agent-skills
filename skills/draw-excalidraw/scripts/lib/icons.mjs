import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fuzzyScore, sha1 } from './util.mjs';

const require = createRequire(import.meta.url);
const cache = new Map();

async function loadSet(provider) {
  const key = provider === 'brand' ? '@iconify-json/simple-icons/icons.json' : '@iconify-json/lucide/icons.json';
  if (cache.has(key)) return cache.get(key);
  const resolved = require.resolve(key);
  const data = JSON.parse(await fs.readFile(resolved, 'utf8'));
  cache.set(key, data);
  return data;
}

export async function searchIcons(query, provider='lucide', limit=20) {
  const data = await loadSet(provider);
  return Object.keys(data.icons)
    .map(name => ({ name, score: fuzzyScore(query, name) }))
    .filter(x => x.score >= 0)
    .sort((a,b)=>b.score-a.score || a.name.localeCompare(b.name))
    .slice(0,limit)
    .map(x=>x.name);
}

export function parseIcon(value, fallbackName='box') {
  if (!value) return {provider:'lucide', name:fallbackName};
  if (typeof value === 'object') return {provider:value.provider || 'lucide', name:value.name || fallbackName};
  const s=String(value);
  const i=s.indexOf(':');
  if (i>0) return {provider:s.slice(0,i), name:s.slice(i+1)};
  return {provider:'lucide', name:s};
}

export async function iconSvgData(provider, name, color='#343a40') {
  if (provider === 'none' || provider === 'library') return null;
  const p = provider === 'brand' ? 'brand' : 'lucide';
  const data = await loadSet(p);
  let icon = data.icons[name];
  if (!icon) {
    const matches = await searchIcons(name, p, 1);
    icon = matches[0] ? data.icons[matches[0]] : null;
    name = matches[0] || name;
  }
  if (!icon) return null;
  const width = icon.width || data.width || 24;
  const height = icon.height || data.height || 24;
  let body = icon.body.replaceAll('currentColor', color);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" fill="none" color="${color}">${body}</svg>`;
  const dataURL = `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
  return { dataURL, width, height, fileId: sha1(`${p}:${name}:${color}`), resolvedName:name };
}
