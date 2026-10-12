"""
Seed script: BNSSA family + all French departments as RegionAnchors.
Run from the project root with the venv active:
    python scripts/seed_data.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make sure the src package is importable when run from the project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from job_aggregator.db.engine import async_session, init_db
from job_aggregator.db.models import JobFamily, JobFamilyKeyword, RegionAnchor

# ── BNSSA family ──────────────────────────────────────────────────────────────

BNSSA_FAMILY = {
    "slug": "bnssa",
    "display_name": "BNSSA / Surveillance aquatique",
    "description": (
        "Maîtres-nageurs, surveillants de baignade, éducateurs sportifs aquatiques "
        "et profils BNSSA / MNS / BEESAN / BPJEPS AAN."
    ),
    "sort_order": 0,
}

# ── MVD family ───────────────────────────────────────────────────────────────

MVD_FAMILY = {
    "slug": "mvd",
    "display_name": "MVD / Maçonnerie Voirie Réseaux",
    "description": (
        "Maçons, terrassiers, canalisateurs, paveurs et profils BTP "
        "Voirie & Réseaux Divers (VRD / TP / Génie Civil)."
    ),
    "sort_order": 10,
}

MVD_KEYWORDS = [
    # Diplômes et certifications
    "CAP VRD",
    "CAP maçonnerie",
    "Bac Pro VRD",
    "BTS Bâtiment",
    "BTS travaux publics",
    "CACES R482",
    "CACES R372",
    # Intitulés de poste
    "maçon",
    "maçonnerie",
    "coffreur",
    "coffreur bancheur",
    "terrassier",
    "canalisateur",
    "paveur",
    "poseur de canalisations",
    "poseur de réseaux",
    "chef de chantier VRD",
    "conducteur de travaux VRD",
    # Domaine
    "VRD",
    "voirie",
    "travaux publics",
    "génie civil",
    "revêtement routier",
    "enrobé",
    "bitume",
    # Réseaux
    "canalisation",
    "tranchée",
    "assainissement",
    "réseau enterré",
    "réseau souterrain",
    "pose de canalisations",
    "terrassement",
]

# ── CDE family ───────────────────────────────────────────────────────────────

CDE_FAMILY = {
    "slug": "cde",
    "display_name": "CDE / Cariste d'entrepôt",
    "description": (
        "Caristes, préparateurs de commandes, conducteurs de chariots élévateurs "
        "et profils logistique entrepôt (CACES R489 / R485)."
    ),
    "sort_order": 20,
}

CDE_KEYWORDS = [
    # Certifications — très spécifiques, clé de voûte du métier
    "CACES R489",
    "CACES R485",
    "CACES R488",
    "CACES 1B",
    "CACES 3",
    "CACES 5",
    "CACES chariot",
    "CACES gerbeur",
    # Intitulés de poste
    "cariste",
    "conducteur de chariot",
    "conducteur de chariot élévateur",
    "préparateur de commandes",
    "magasinier cariste",
    "agent logistique",
    "opérateur logistique",
    # Équipements
    "chariot élévateur",
    "chariot télescopique",
    "gerbeur",
    "transpalette électrique",
    "transpalette à conducteur porté",
    # Tâches et environnement
    "palettisation",
    "picking",
    "préparation de commandes",
    "entrepôt logistique",
    "quai de chargement",
    "gestion des stocks",
]

# ── AMU family ───────────────────────────────────────────────────────────────

AMU_FAMILY = {
    "slug": "amu",
    "display_name": "AMU / Manager d'unité marchande",
    "description": (
        "Chefs de rayon, managers de rayon, responsables d'unité marchande "
        "et encadrants grande distribution (BTS MCO / MUC)."
    ),
    "sort_order": 30,
}

AMU_KEYWORDS = [
    # Diplômes
    "BTS MCO",
    "BTS MUC",
    "licence pro commerce",
    "licence pro distribution",
    "DUT techniques de commercialisation",
    # Intitulés de poste
    "manager d'unité marchande",
    "manager de rayon",
    "chef de rayon",
    "responsable de rayon",
    "chef de département",
    "directeur adjoint de magasin",
    "adjoint responsable de magasin",
    "animateur des ventes",
    "responsable commercial magasin",
    # Opérationnel
    "gestion de rayon",
    "implantation rayon",
    "merchandising",
    "animation commerciale",
    "linéaire",
    "assortiment produits",
    # Secteur
    "grande distribution",
    "GMS",
    "GSS",
    "hypermarché",
    "supermarché",
    "enseigne commerciale",
]

# ── BNSSA family keywords ─────────────────────────────────────────────────────

BNSSA_KEYWORDS = [
    # Diplômes et certifications
    "BNSSA",
    "MNS",
    "BEESAN",
    "BPJEPS AAN",
    "BPJEPS aquatique",
    "BPJEPS natation",
    "BSB",
    "NSP",
    # Intitulés de poste
    "maître nageur",
    "maître-nageur",
    "nageur sauveteur",
    "surveillant de baignade",
    "surveillant baignade",
    "éducateur sportif natation",
    "éducateur aquatique",
    "animateur natation",
    "animateur aquatique",
    "moniteur natation",
    "moniteur aquatique",
    "responsable bassin",
    "chef de bassin",
    "directeur de bassin",
    # Environnements / structures
    "piscine municipale",
    "piscine publique",
    "bassin de natation",
    "BNSSA obligatoire",
    "surveillance aquatique",
    "parc aquatique",
    "centre nautique",
    "centre aquatique",
    "complexe aquatique",
    # Sécurité
    "sécurité aquatique",
    "sauvetage aquatique",
]

# ── Départements français ─────────────────────────────────────────────────────
# (code, display_name, center_lat, center_lon)

DEPARTMENTS: list[tuple[str, str, float, float]] = [
    ("01", "Ain", 46.2044, 5.2263),
    ("02", "Aisne", 49.5650, 3.6220),
    ("03", "Allier", 46.5654, 3.2941),
    ("04", "Alpes-de-Haute-Provence", 44.0652, 6.2315),
    ("05", "Hautes-Alpes", 44.6612, 6.3428),
    ("06", "Alpes-Maritimes", 43.9352, 7.1079),
    ("07", "Ardèche", 44.7489, 4.6002),
    ("08", "Ardennes", 49.6920, 4.7157),
    ("09", "Ariège", 42.9671, 1.6052),
    ("10", "Aube", 48.3060, 4.0808),
    ("11", "Aude", 43.2050, 2.3490),
    ("12", "Aveyron", 44.3512, 2.5746),
    ("13", "Bouches-du-Rhône", 43.5297, 5.4474),
    ("14", "Calvados", 49.1805, -0.3706),
    ("15", "Cantal", 45.0472, 2.6221),
    ("16", "Charente", 45.6964, 0.1597),
    ("17", "Charente-Maritime", 45.7481, -0.6703),
    ("18", "Cher", 47.0843, 2.3965),
    ("19", "Corrèze", 45.3677, 1.8721),
    ("2A", "Corse-du-Sud", 41.8621, 8.9751),
    ("2B", "Haute-Corse", 42.3676, 9.1837),
    ("21", "Côte-d'Or", 47.3218, 5.0418),
    ("22", "Côtes-d'Armor", 48.5146, -2.7603),
    ("23", "Creuse", 46.1071, 2.0243),
    ("24", "Dordogne", 45.1830, 0.7210),
    ("25", "Doubs", 47.2360, 6.4215),
    ("26", "Drôme", 44.7231, 5.0000),
    ("27", "Eure", 49.0977, 1.1523),
    ("28", "Eure-et-Loir", 48.4468, 1.4897),
    ("29", "Finistère", 48.2341, -4.1628),
    ("30", "Gard", 43.9503, 4.1427),
    ("31", "Haute-Garonne", 43.6047, 1.4442),
    ("32", "Gers", 43.6455, 0.5872),
    ("33", "Gironde", 44.8378, -0.5792),
    ("34", "Hérault", 43.6119, 3.8772),
    ("35", "Ille-et-Vilaine", 48.1173, -1.6778),
    ("36", "Indre", 46.8151, 1.6914),
    ("37", "Indre-et-Loire", 47.3941, 0.6848),
    ("38", "Isère", 45.1885, 5.7245),
    ("39", "Jura", 46.6727, 5.5553),
    ("40", "Landes", 43.9494, -0.5992),
    ("41", "Loir-et-Cher", 47.5870, 1.3361),
    ("42", "Loire", 45.7597, 4.1325),
    ("43", "Haute-Loire", 45.0428, 3.8840),
    ("44", "Loire-Atlantique", 47.2184, -1.5536),
    ("45", "Loiret", 47.9030, 1.9090),
    ("46", "Lot", 44.4468, 1.4415),
    ("47", "Lot-et-Garonne", 44.3512, 0.5163),
    ("48", "Lozère", 44.5197, 3.4992),
    ("49", "Maine-et-Loire", 47.4667, -0.5552),
    ("50", "Manche", 49.1177, -1.3108),
    ("51", "Marne", 49.0432, 4.0649),
    ("52", "Haute-Marne", 48.1094, 5.1381),
    ("53", "Mayenne", 48.2968, -0.7001),
    ("54", "Meurthe-et-Moselle", 48.6921, 6.1844),
    ("55", "Meuse", 48.9965, 5.3596),
    ("56", "Morbihan", 47.8571, -2.7561),
    ("57", "Moselle", 49.1197, 6.1757),
    ("58", "Nièvre", 47.2153, 3.3284),
    ("59", "Nord", 50.6292, 3.0573),
    ("60", "Oise", 49.3647, 2.4090),
    ("61", "Orne", 48.6234, 0.0877),
    ("62", "Pas-de-Calais", 50.5152, 2.6332),
    ("63", "Puy-de-Dôme", 45.7772, 3.0875),
    ("64", "Pyrénées-Atlantiques", 43.2951, -0.3708),
    ("65", "Hautes-Pyrénées", 43.2328, 0.0778),
    ("66", "Pyrénées-Orientales", 42.6989, 2.8951),
    ("67", "Bas-Rhin", 48.5734, 7.7521),
    ("68", "Haut-Rhin", 47.7486, 7.3398),
    ("69", "Rhône", 45.7597, 4.8422),
    ("70", "Haute-Saône", 47.6225, 6.1559),
    ("71", "Saône-et-Loire", 46.6537, 4.4630),
    ("72", "Sarthe", 47.9950, 0.1916),
    ("73", "Savoie", 45.5646, 6.3936),
    ("74", "Haute-Savoie", 45.8992, 6.1294),
    ("75", "Paris", 48.8566, 2.3522),
    ("76", "Seine-Maritime", 49.4431, 1.0993),
    ("77", "Seine-et-Marne", 48.6084, 2.8870),
    ("78", "Yvelines", 48.8014, 1.9871),
    ("79", "Deux-Sèvres", 46.5523, -0.3326),
    ("80", "Somme", 49.9216, 2.2967),
    ("81", "Tarn", 43.7967, 2.1489),
    ("82", "Tarn-et-Garonne", 44.0161, 1.3520),
    ("83", "Var", 43.4667, 6.2165),
    ("84", "Vaucluse", 43.9493, 5.0868),
    ("85", "Vendée", 46.6702, -1.4269),
    ("86", "Vienne", 46.5802, 0.3404),
    ("87", "Haute-Vienne", 45.8354, 1.2625),
    ("88", "Vosges", 48.2093, 6.4454),
    ("89", "Yonne", 47.7982, 3.5674),
    ("90", "Territoire de Belfort", 47.6382, 6.8630),
    ("91", "Essonne", 48.4765, 2.1624),
    ("92", "Hauts-de-Seine", 48.8924, 2.2368),
    ("93", "Seine-Saint-Denis", 48.9357, 2.3544),
    ("94", "Val-de-Marne", 48.7886, 2.4699),
    ("95", "Val-d'Oise", 49.0580, 2.1228),
    ("971", "Guadeloupe", 16.2650, -61.5510),
    ("972", "Martinique", 14.6415, -61.0242),
    ("973", "Guyane", 4.9224, -52.3135),
    ("974", "La Réunion", -21.1151, 55.5364),
    ("976", "Mayotte", -12.8275, 45.1662),
]


async def _upsert_family(session, family_def: dict, keywords: list[str]) -> None:
    """Create or update a family and add any missing keywords. Idempotent."""
    result = await session.execute(
        select(JobFamily).where(JobFamily.slug == family_def["slug"])
    )
    family = result.scalar_one_or_none()

    if family is None:
        family = JobFamily(**family_def)
        session.add(family)
        await session.flush()
        print(f"✓  Created family: {family.display_name} ({family.id})")
    else:
        print(f"→  Family already exists: {family.display_name} ({family.id})")

    existing_kws_result = await session.execute(
        select(JobFamilyKeyword.keyword).where(JobFamilyKeyword.family_id == family.id)
    )
    existing_kws = {row[0] for row in existing_kws_result.all()}

    # dict.fromkeys drops repeated keywords (keeping order) so a duplicate in a
    # list cannot violate uq_family_keyword.
    added = [kw for kw in dict.fromkeys(keywords) if kw not in existing_kws]
    for kw in added:
        session.add(JobFamilyKeyword(family_id=family.id, keyword=kw))

    if added:
        print(f"   + {len(added)} keywords added")
    else:
        print("   Keywords already up to date")

    await session.commit()


async def seed() -> None:
    await init_db()

    async with async_session() as session:
        await _upsert_family(session, BNSSA_FAMILY, BNSSA_KEYWORDS)
        await _upsert_family(session, MVD_FAMILY, MVD_KEYWORDS)
        await _upsert_family(session, CDE_FAMILY, CDE_KEYWORDS)
        await _upsert_family(session, AMU_FAMILY, AMU_KEYWORDS)

        # ── Departments ───────────────────────────────────────────────────────
        created = 0
        skipped = 0
        for code, name, lat, lon in DEPARTMENTS:
            slug = f"dept-{code.lower()}"
            stmt = (
                pg_insert(RegionAnchor)
                .values(
                    slug=slug,
                    display_name=f"{code} – {name}",
                    center_lat=lat,
                    center_lon=lon,
                    department_codes=[code],
                )
                .on_conflict_do_nothing(index_elements=["slug"])
                .returning(RegionAnchor.id)
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            if row:
                created += 1
            else:
                skipped += 1

        await session.commit()
        print(f"✓  Departments: {created} created, {skipped} already present")


if __name__ == "__main__":
    asyncio.run(seed())
