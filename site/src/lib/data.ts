import fs from 'node:fs';
import path from 'node:path';
import { load as yamlLoad } from 'js-yaml';

const ROOT = path.resolve(process.cwd(), '..');
const DATA = path.join(ROOT, 'data');
const read = (p: string) => fs.readFileSync(path.join(DATA, p), 'utf8');
// Dates stay strings: YAML timestamps are converted back to ISO dates.
const norm = (v: any): any =>
  v instanceof Date ? v.toISOString().slice(0, 10) : Array.isArray(v) ? v.map(norm) : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, norm(x)])) : v;
const readYaml = <T>(p: string) => norm(yamlLoad(read(p))) as T;
const exists = (p: string) => fs.existsSync(path.join(DATA, p));

export const SITE_NAME = 'BIOPOLYMER Intelligence';
export const REPO = 'https://github.com/rethinksci-gif/biopolymer-intelligence';
export const SITE_URL = 'https://rethinksci-gif.github.io/biopolymer-intelligence/';
export const SISTER = { name: 'BIOGLUE Intelligence', url: 'https://rethinksci-gif.github.io/bioglue-intelligence/' };
export const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
export const url = (p: string) => `${BASE}/${p}`;

export interface Support { ref: string; quote: string }
export interface Route {
  id: string; label: string; family: string; focus: boolean; name: string; tagline: string; scope: string;
  what: string[]; chemistry: string[]; production: string[]; properties: string[];
  eol: Record<'bio_based_origin' | 'biodegradability' | 'compostability' | 'recyclability', string>;
  key_players: { name: string; ref: string }[]; applications: string[]; challenges: string[]; challenge_links: string[];
  structures: string[]; refs: string[]; support?: Support[];
}
export interface Structure { id: string; name: string; role_label: string; role: string; smiles: string; routes: string[]; inchikey?: string; cid?: number; hydrolysis?: string[]; ref: string; benchmark?: boolean }
export interface Reference { id: string; authors: string; year: number; title: string; journal: string; doi: string; kind: string; routes: string[] }
export interface Challenge { id: string; title: string; why: string; measured: string; evidence: string; refs: string[]; sources?: string[]; routes: string[] }
export interface SourceQuote { id: string; text: string; display?: string; translation?: string }
export interface OfficialSource { id: string; issuer: string; title: string; reference: string; date: string | null; url: string; retrieved: string; language: string; quotes: SourceQuote[] }
export interface Block { heading: string; text: string; structures?: string[]; refs: string[]; sources?: string[] }
export interface Section { id: string; number: string; title: string; lede: string; figure: string | null; figure_kind?: string; blocks: Block[]; support?: Support[]; table?: string }
export interface Lead {
  id: string; title: string; url: string; doi: string | null; venue: string; authors: string; source_type: string; published_date: string;
  date_precision?: string; language: string; route: string; novelty_type: string; relevance: number; signal_type: string; region: string;
  summary: string; quote: string; quote_location: string | null; hidden: boolean; flags: string[]; triaged_at?: string; model?: string; run_id?: string;
}
export interface LeadFile { month: string; window: [string, string]; scanned_through: string; status: string; updated: string; triage_model: string | null; triage_pending: number; note: string; leads: Lead[] }
export interface Run { run_id: string; month: string; started: string; finished: string; scanned_through: string; triage: string; triage_model: string | null; budget: number; llm_calls: number; usage: { prompt_tokens: number; completion_tokens: number }; cost_usd: number | null; discovered: number; keyword_gate_rejected?: number; sent_to_llm: number; shown: number; triage_pending: number; discovery_errors: string[] }
export interface Development { id: string; month: string; title: string; route: string; label: string; novelty_type: string; event: string; published_date: string | null; sources: { url: string; doi?: string | null; locator?: string; quote?: string }[]; review: { status: string; reviewer: string | null; date: string | null }; attributes: Record<string, { value: string; quote?: string; source?: string }>; [k: string]: any }
export interface Issue { id: string; title: string; window: [string, string]; cutoff: string; status: string; layout_status: string; review: { reviewer: string | null; date: string | null }; what_changed: string | null; notes?: string[]; cards?: any[]; watchlist?: string[]; questions?: string[]; shortlist?: { lead_id: string; why: string; evidence_status?: string }[] }
export interface Build { month: string; built: string; pages: number | null; words: number; body_pt: number; problems: string[]; html: string; pdf: string | null; cover: string | null }

export const routes = readYaml<Route[]>('routes.yaml');
export const structures = readYaml<Structure[]>('structures.yaml');
export const references = readYaml<Reference[]>('references.yaml');
export const challenges = readYaml<Challenge[]>('challenges.yaml');
export const glossary = readYaml<{ terms: { term: string; text: string }[]; labels: { term: string; text: string }[]; standards: { code: string; title: string; body: string; url: string; note?: string }[]; domain_reference: { source: string } }>('glossary.yaml');
export const chemistry = readYaml<{ sections: Section[]; eol_matrix: any }>('chemistry.yaml');
export const properties = readYaml<{ columns: { id: string; label: string; unit: string }[]; rows: { id: string; polymer: string; route: string; values: Record<string, any> }[] }>('properties.yaml');
export const sources = readYaml<OfficialSource[]>('sources.yaml');
export const editorial = readYaml<any>('editorial.yaml');

const jsonDir = <T>(dir: string): T[] => {
  const d = path.join(DATA, dir);
  if (!fs.existsSync(d)) return [];
  return fs.readdirSync(d).filter((f) => /^\d{4}-\d{2}\.json$/.test(f)).sort().map((f) => JSON.parse(fs.readFileSync(path.join(d, f), 'utf8')) as T);
};
export const leadFiles = jsonDir<LeadFile>('leads');
export const runFiles = jsonDir<{ month: string; runs: Run[] }>('runs');
export const developments: Record<string, Development[]> = Object.fromEntries(
  (exists('developments') ? fs.readdirSync(path.join(DATA, 'developments')) : []).filter((f) => f.endsWith('.yaml')).map((f) => [f.slice(0, 7), readYaml<Development[]>(`developments/${f}`) ?? []]),
);
export const issues: Issue[] = (exists('newsletter') ? fs.readdirSync(path.join(DATA, 'newsletter')) : [])
  .filter((f) => /^\d{4}-\d{2}\.yaml$/.test(f)).sort().reverse().map((f) => ({ ...readYaml<Issue>(`newsletter/${f}`), id: f.slice(0, 7) }));
export const buildOf = (m: string): Build | null => (exists(`newsletter/${m}.build.json`) ? JSON.parse(read(`newsletter/${m}.build.json`)) : null);
export const verification = exists('cache/verification.json') ? JSON.parse(read('cache/verification.json')) : null;

/** Months with any data, newest first. */
export const MONTHS = [...new Set([...leadFiles.map((l) => l.month), ...Object.keys(developments), ...issues.map((i) => i.id)])].sort().reverse();
export const LATEST = MONTHS.find((m) => leadFiles.find((l) => l.month === m)?.status === 'complete') ?? MONTHS[0];
export const monthLabel = (m: string) => new Date(m + '-01T00:00:00Z').toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
export const fmtDate = (d: string | null | undefined) =>
  d ? new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : 'Date not established';

export const routeById = (id: string) => routes.find((r) => r.id === id);
export const refById = (id: string) => references.find((r) => r.id === id);
export const molById = (id: string) => structures.find((s) => s.id === id);
export const sourceById = (id: string) => sources.find((s) => s.id === id);
export const sourceQuote = (key: string) => {
  const [sid, qid] = key.split('#');
  const s = sourceById(sid);
  return { source: s, quote: qid ? s?.quotes.find((q) => q.id === qid) : undefined };
};
export const challengeById = (id: string) => challenges.find((c) => c.id === id);
export const leadFile = (m: string) => leadFiles.find((x) => x.month === m);
export const shownLeads = (m: string, route?: string) => (leadFile(m)?.leads ?? []).filter((c) => !c.hidden && (!route || c.route === route));
export const devsFor = (m: string, route?: string) => (developments[m] ?? []).filter((d) => !route || d.route === route);
export const leadsYTD = (year: string) => leadFiles.filter((l) => l.month.startsWith(year)).reduce((n, l) => n + l.leads.filter((c) => !c.hidden).length, 0);
export const refLink = (r: Reference) => `https://doi.org/${r.doi}`;
export const structureSvg = (id: string) => {
  const p = path.join(process.cwd(), 'src', 'generated', 'structures', `${id}.svg`);
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : '';
};
export const NOVELTY: Record<string, string> = Object.fromEntries((editorial.novelty_types as any[]).map((n) => [n.id, n.label]));
export const runsFor = (m: string) => runFiles.find((r) => r.month === m)?.runs ?? [];
export const lastRun = () => runFiles.flatMap((r) => r.runs).sort((a, b) => a.finished.localeCompare(b.finished)).at(-1);
