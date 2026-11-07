#!/usr/bin/env node
// Minimal example implementation of the file-organizer skill.
// Usage: node index.js <directory> [--dry-run]
const fs = require('fs');
const path = require('path');

const CATEGORIES = {
  images: ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'],
  documents: ['.doc', '.docx', '.pdf', '.txt', '.md', '.xls', '.xlsx', '.ppt', '.pptx'],
  code: ['.js', '.ts', '.py', '.java', '.cpp', '.c', '.html', '.css', '.json'],
  videos: ['.mp4', '.avi', '.mov', '.wmv', '.flv'],
  audio: ['.mp3', '.wav', '.flac', '.aac', '.ogg'],
  archives: ['.zip', '.rar', '.7z', '.tar', '.gz'],
};

function category(file) {
  const ext = path.extname(file).toLowerCase();
  for (const [name, exts] of Object.entries(CATEGORIES)) {
    if (exts.includes(ext)) return name;
  }
  return 'others';
}

function main() {
  const [dir, ...flags] = process.argv.slice(2);
  if (!dir) { console.error('usage: node index.js <directory> [--dry-run]'); process.exit(1); }
  const dryRun = flags.includes('--dry-run');
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const target = category(entry.name);
    const dest = path.join(dir, target, entry.name);
    console.log(`${entry.name} -> ${target}/`);
    if (dryRun) continue;
    fs.mkdirSync(path.join(dir, target), { recursive: true });
    fs.renameSync(path.join(dir, entry.name), dest);
  }
}

main();
