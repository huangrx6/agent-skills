import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readJson } from './util.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');

export async function loadTheme(name='technical') {
  const safe = ['technical','presentation','monochrome'].includes(name) ? name : 'technical';
  return readJson(path.join(root, 'themes', `${safe}.json`));
}

const defaultIcons = {
  user: 'user', client: 'monitor', gateway: 'router', api: 'plug-zap', service: 'box', worker: 'cpu',
  database: 'database', cache: 'database-zap', queue: 'messages-square', security: 'shield-check',
  external: 'cloud', decision: 'git-branch', default: 'box'
};

export function styleForKind(theme, kind='default') {
  const p = theme.palette[kind] || theme.palette.default;
  return { backgroundColor: p[0], strokeColor: p[1], icon: defaultIcons[kind] || defaultIcons.default };
}
