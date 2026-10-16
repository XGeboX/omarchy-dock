#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = (root / 'plugin/DockMotion.js').read_text().replace('.pragma library\n', '')
(root / 'integrations/gnome/motion.js').write_text(source.replace('function ', 'export function '))
