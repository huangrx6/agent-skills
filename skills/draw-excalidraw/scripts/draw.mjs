#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { compileSpec } from './lib/compiler.mjs';
import { lintSpec } from './lib/lint.mjs';
import { writePreview } from './lib/preview.mjs';
import { readJson, writeJson, exists } from './lib/util.mjs';
import { searchIcons } from './lib/icons.mjs';
import { syncCatalog, searchCatalog, installLibrary, searchInstalledItems, skillRoot } from './lib/libraries.mjs';

function parseArgs(argv){const out={_:[]};for(let i=0;i<argv.length;i++){const a=argv[i];if(a.startsWith('--')){const k=a.slice(2);const v=argv[i+1]&&!argv[i+1].startsWith('--')?argv[++i]:true;out[k]=v;}else out._.push(a);}return out;}
function usage(){console.log(`draw-excalidraw\n\nCommands:\n  doctor\n  build --spec <file> --out <file.excalidraw> [--preview <file.svg>]\n  lint --spec <file>\n  icon search <query> [--provider lucide|brand]\n  library sync\n  library search <query>\n  library install <id-or-name>\n  library items <query>\n`);}

async function doctor(){
  const checks=[]; const major=Number(process.versions.node.split('.')[0]); checks.push(['Node >=20',major>=20,process.versions.node]);
  for(const pkg of ['@dagrejs/dagre','elkjs','@iconify-json/lucide','@iconify-json/simple-icons']){try{await import(pkg==='elkjs'?'elkjs/lib/elk.bundled.js':pkg);checks.push([pkg,true,'ok']);}catch(e){checks.push([pkg,false,'run npm install in skill directory']);}}
  console.log(`skillRoot: ${skillRoot}`); for(const [name,ok,msg] of checks)console.log(`${ok?'✓':'✗'} ${name}: ${msg}`); if(checks.some(x=>!x[1]))process.exitCode=2;
}

async function build(args){if(!args.spec||!args.out)throw new Error('build requires --spec and --out');const spec=await readJson(args.spec);if(args.theme)spec.theme=args.theme;if(args.engine)spec.layout={...(spec.layout||{}),engine:args.engine};const compiled=await compileSpec(spec);const issues=lintSpec(spec,compiled);await writeJson(args.out,compiled.scene);if(args.preview)await writePreview(compiled.scene,args.preview);const errors=issues.filter(x=>x.level==='error');console.log(`wrote ${args.out} (${compiled.scene.elements.length} elements, ${Object.keys(compiled.scene.files).length} embedded files)`);if(args.preview)console.log(`wrote ${args.preview}`);if(issues.length){console.log('lint:');issues.forEach(x=>console.log(`  ${x.level.toUpperCase()} ${x.code}: ${x.message}`));}else console.log('lint: clean');if(errors.length)process.exitCode=3;}

async function lint(args){if(!args.spec)throw new Error('lint requires --spec');const spec=await readJson(args.spec);const compiled=await compileSpec(spec);const issues=lintSpec(spec,compiled);issues.forEach(x=>console.log(`${x.level.toUpperCase()} ${x.code}: ${x.message}`));if(!issues.length)console.log('clean');if(issues.some(x=>x.level==='error'))process.exitCode=3;}

async function main(){const argv=process.argv.slice(2),cmd=argv[0],args=parseArgs(argv.slice(1));if(!cmd||cmd==='help'||cmd==='--help')return usage();if(cmd==='doctor')return doctor();if(cmd==='build')return build(args);if(cmd==='lint')return lint(args);if(cmd==='icon'&&args._[0]==='search'){const q=args._.slice(1).join(' ');const provider=args.provider||'lucide';(await searchIcons(q,provider,30)).forEach(x=>console.log(`${provider}:${x}`));return;}if(cmd==='library'){const sub=args._[0];const q=args._.slice(1).join(' ');if(sub==='sync'){console.log(`catalog entries: ${await syncCatalog()}`);return;}if(sub==='search'){(await searchCatalog(q,30)).forEach(x=>console.log(`${x.id}\t${x.name}\t${x.description||''}`));return;}if(sub==='install'){const r=await installLibrary(q);console.log(`installed ${r.item.name} -> ${r.dest}`);return;}if(sub==='items'){(await searchInstalledItems(q,30)).forEach(x=>console.log(`${x.name}\t${x.file}`));return;}}usage();process.exitCode=1;}
main().catch(e=>{console.error(`draw-excalidraw: ${e.stack||e.message}`);process.exit(1);});
