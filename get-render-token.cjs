// Helper local ( non commité ) : lit la clé API Render.
const fs = require('fs');
const os = require('os');
const path = require('path');
const yaml = require('yaml');
const f = path.join(os.homedir(), '.render', 'cli.yaml');
const doc = yaml.parse(fs.readFileSync(f, 'utf8'));
process.stdout.write(doc.api.key);
