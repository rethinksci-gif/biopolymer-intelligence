import { routes, structures, challenges, references, leadFiles, developments, issues } from '../../lib/data';
const strip = ({ abstract, query, seed_routes, hash, ...rest }: any) => rest;
const files: Record<string, unknown[] | object> = {
  routes: routes.map(({ scan, ...r }) => r), structures, challenges, references,
  ...Object.fromEntries(leadFiles.map((l) => [`leads/${l.month}`, { ...l, leads: l.leads.filter((x) => !x.hidden).map(strip) }])),
  ...Object.fromEntries(Object.entries(developments).map(([m, d]) => [`developments/${m}`, d])),
  ...Object.fromEntries(issues.map((n) => [`newsletter/${n.id}`, n])),
};
const csvCols: Record<string, string[]> = {
  routes: ['id', 'label', 'name', 'tagline', 'scope'],
  structures: ['id', 'name', 'role_label', 'smiles', 'inchikey', 'cid', 'routes', 'ref'],
  references: ['id', 'authors', 'year', 'title', 'journal', 'doi', 'kind', 'routes'],
  leads: ['id', 'published_date', 'route', 'novelty_type', 'relevance', 'source_type', 'venue', 'title', 'summary', 'quote', 'url', 'doi'],
  developments: ['id', 'month', 'route', 'label', 'novelty_type', 'title', 'published_date'],
};
const cell = (v: unknown) => { const s = Array.isArray(v) ? v.join(';') : v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const toCsv = (rows: any[], cols: string[]) => [cols.join(','), ...rows.map((r) => cols.map((c) => cell(r[c])).join(','))].join('\n') + '\n';
const rowsOf = (k: string, v: any) => (Array.isArray(v) ? v : v.leads ?? []);
export function getStaticPaths() {
  const out: { params: { file: string } }[] = [];
  for (const k of Object.keys(files)) {
    out.push({ params: { file: `${k}.json` } });
    const base = k.split('/')[0];
    if (csvCols[base]) out.push({ params: { file: `${k}.csv` } });
  }
  return out;
}
export function GET({ params }: { params: { file: string } }) {
  const [key, ext] = [params.file.replace(/\.(json|csv)$/, ''), params.file.split('.').pop()];
  const v = files[key];
  if (ext === 'csv') return new Response(toCsv(rowsOf(key, v), csvCols[key.split('/')[0]]), { headers: { 'Content-Type': 'text/csv; charset=utf-8' } });
  return new Response(JSON.stringify(v, null, 2), { headers: { 'Content-Type': 'application/json' } });
}
