import { references } from '../lib/data';
export function GET() {
  const esc = (s: string) => s.replace(/[{}]/g, '');
  const body = references.map((r) => {
    const fields = [`title = {${esc(r.title)}}`, `author = {${esc(r.authors.replace(/ et al\.$/, ' and others').replace(/\., /g, '. and '))}}`, `year = {${r.year}}`, `journal = {${esc(r.journal)}}`, `doi = {${r.doi}}`];
    return `@article{${r.id},\n  ${fields.join(',\n  ')}\n}`;
  }).join('\n\n');
  return new Response(body + '\n', { headers: { 'Content-Type': 'application/x-bibtex; charset=utf-8' } });
}
