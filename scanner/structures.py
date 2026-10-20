"""Verify data/structures.yaml against PubChem and render theme-aware SVGs with RDKit (build time only).

A structure that fails verification stops the build: an unverified drawing is never published."""
from __future__ import annotations

import json
import re
import urllib.parse

from .config import CACHE, ROOT, load
from .http import get_json

OUT = ROOT / "site" / "src" / "generated" / "structures"
PUBCHEM_CACHE = CACHE / "pubchem.json"


class StructureError(ValueError):
    pass


def pubchem_inchikey(cid: int, cache: dict, offline: bool = False) -> str:
    key = str(cid)
    if key not in cache:
        if offline:
            raise StructureError(f"CID {cid} not in {PUBCHEM_CACHE.name}; run `python -m scanner structures --refresh`")
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/InChIKey,IUPACName/JSON"
        p = get_json(url)["PropertyTable"]["Properties"][0]
        cache[key] = {"inchikey": p["InChIKey"], "iupac": p.get("IUPACName", "")}
    return cache[key]["inchikey"]


def cap_and_hydrolyse(smiles: str):
    """Cap a repeat unit (-O*/-N* -> H, C(*)=O -> C(=O)OH) and hydrolyse every ester/amide bond.
    Returns the set of InChIKeys of the fragments."""
    from rdkit import Chem

    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
    for atom in sorted((a for a in mol.GetAtoms() if a.GetAtomicNum() == 0), key=lambda a: -a.GetIdx()):
        nb = atom.GetNeighbors()[0]
        if nb.GetSymbol() == "C":
            atom.SetAtomicNum(8)  # becomes the OH of a carboxylic acid
        else:
            mol.RemoveAtom(atom.GetIdx())
    mol = mol.GetMol()
    Chem.SanitizeMol(mol)
    rw = Chem.RWMol(mol)
    for c, _, x in rw.GetSubstructMatches(Chem.MolFromSmarts("[CX3](=O)-[OX2H0,NX3]")):
        if rw.GetBondBetweenAtoms(c, x) is None:
            continue
        rw.RemoveBond(c, x)
        oh = rw.AddAtom(Chem.Atom(8))  # acyl side gets OH; the O/N side keeps an H implicitly
        rw.AddBond(c, oh, Chem.BondType.SINGLE)
    frag = rw.GetMol()
    for a in frag.GetAtoms():
        a.SetNoImplicit(False)
        a.SetNumExplicitHs(0)
    Chem.SanitizeMol(frag)
    return {Chem.MolToInchiKey(m) for m in Chem.GetMolFrags(frag, asMols=True)}


def verify(offline: bool = False) -> list[str]:
    from rdkit import Chem

    mols = load("structures")
    by_id = {m["id"]: m for m in mols}
    cache = json.loads(PUBCHEM_CACHE.read_text()) if PUBCHEM_CACHE.exists() else {}
    errors = []
    for m in mols:
        mol = Chem.MolFromSmiles(m["smiles"])
        if mol is None:
            errors.append(f"{m['id']}: invalid SMILES")
            continue
        if "cid" in m:
            ik = Chem.MolToInchiKey(mol)
            try:
                pk = pubchem_inchikey(m["cid"], cache, offline)
            except Exception as exc:
                errors.append(f"{m['id']}: PubChem lookup failed ({exc})")
                continue
            if ik != pk:
                errors.append(f"{m['id']}: InChIKey {ik} does not match PubChem CID {m['cid']} ({pk})")
            if m.get("inchikey") != pk:
                errors.append(f"{m['id']}: stored inchikey {m.get('inchikey')} differs from PubChem ({pk})")
        elif "hydrolysis" in m:
            got = cap_and_hydrolyse(m["smiles"])
            want = {by_id[c]["inchikey"] for c in m["hydrolysis"]}
            if got != want:
                errors.append(f"{m['id']}: hydrolysis products {sorted(got)} != {m['hydrolysis']} {sorted(want)}")
        else:
            errors.append(f"{m['id']}: no verification route (needs `cid` or `hydrolysis`)")
    CACHE.mkdir(parents=True, exist_ok=True)
    PUBCHEM_CACHE.write_text(json.dumps(dict(sorted(cache.items())), indent=1) + "\n")
    return errors


def _svg(mol, name: str, repeat: bool) -> str:
    from rdkit.Chem.Draw import rdMolDraw2D

    d = rdMolDraw2D.MolDraw2DSVG(320, 220)
    opts = d.drawOptions()
    opts.clearBackground = False
    opts.bondLineWidth = 2
    opts.padding = 0.14
    opts.fixedBondLength = 34  # same scale for every molecule
    opts.addStereoAnnotation = False
    opts.dummiesAreAttachments = repeat  # draw * as wavy attachment points
    d.DrawMolecule(mol)
    d.FinishDrawing()
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", d.GetDrawingText())
    svg = svg.replace("#000000", "currentColor").replace("#FFFFFF", "none")
    svg = (svg.replace("#FF0000", "var(--atom-o)").replace("#0000FF", "var(--atom-n)")
              .replace("#33CCCC", "var(--atom-n)").replace("#E0E0E0", "currentColor"))
    label = f"{name} {'repeat unit' if repeat else 'structure'}"
    return svg.replace("<svg ", f'<svg role="img" aria-label="{label}" ', 1)


def render(offline: bool = False) -> list[str]:
    from rdkit import Chem

    errors = verify(offline)
    if errors:
        raise StructureError("structure verification failed:\n  " + "\n  ".join(errors))
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    for m in load("structures"):
        repeat = m["role_label"] == "repeat unit"
        svg = _svg(Chem.MolFromSmiles(m["smiles"]), m["name"], repeat)
        if repeat:
            svg = _bracket(svg)
        (OUT / f"{m['id']}.svg").write_text(svg)
        done.append(m["id"])
    return done


def _bracket(svg: str) -> str:
    """Overlay polymer repeat brackets with subscript n on a repeat-unit drawing."""
    br = ('<g fill="none" stroke="currentColor" stroke-width="2">'
          '<path d="M24,40 h-10 v140 h10"/><path d="M296,40 h10 v140 h-10"/></g>'
          '<text x="308" y="200" font-size="18" font-style="italic" fill="currentColor" font-family="serif">n</text>')
    return svg.replace("</svg>", br + "</svg>")
