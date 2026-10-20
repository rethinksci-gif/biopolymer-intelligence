import { SITE_NAME, SITE_URL, MONTHS, shownLeads, devsFor, issues, routeById, monthLabel } from '../lib/data';
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export function GET() {
  const items: { title: string; link: string; date: string; desc: string }[] = [];
  for (const m of MONTHS) {
    for (const d of devsFor(m)) items.push({ title: `[checked] ${d.title}`, link: `${SITE_URL}tracker/${m}/#${d.id}`, date: d.published_date ?? `${m}-01`, desc: d.event });
    for (const c of shownLeads(m)) items.push({ title: `[lead · ${routeById(c.route)?.name}] ${c.title}`, link: c.url, date: c.published_date, desc: `${c.summary} (machine-triaged, not verified)` });
  }
  for (const n of issues) items.push({ title: `[newsletter · ${n.status}] ${n.title}`, link: `${SITE_URL}newsletter/${n.id}/`, date: n.cutoff, desc: `BIOPOLYMER Monthly, ${monthLabel(n.id)}. Status: ${n.status}.` });
  items.sort((a, b) => b.date.localeCompare(a.date));
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>${SITE_NAME}</title><link>${SITE_URL}</link><description>Bio-based polymer developments: checked developments, machine-triaged leads and newsletter issues.</description>${items.slice(0, 150).map((i) => `<item><title>${esc(i.title)}</title><link>${esc(i.link)}</link><guid>${esc(i.link)}</guid><pubDate>${new Date(i.date + 'T00:00:00Z').toUTCString()}</pubDate><description>${esc(i.desc)}</description></item>`).join('')}</channel></rss>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
