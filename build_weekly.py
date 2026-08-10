"""
build_b2b_weekly.py — Rend le B2B Weekly Review Teatower en HTML statique.

Meme langage visuel que le morning dashboard (CSS partagee via `b2b_style.py`),
mais une lecture hebdo : ou on en est, ce qui bouge, et ce qu'il reste a faire.

Lit `reports/b2b_weekly_data.json` (produit par b2b_weekly_extract.py) et ecrit :
  - reports/b2b_weekly_review_YYYY-Sxx.html            (archive datee)
  - reports/b2b-dashboard-deploy/weekly/index.html     (--deploy : page publiee)
  - reports/b2b-dashboard-deploy/weekly/data.json      (--deploy : donnees brutes)

Usage :
  python reports/build_b2b_weekly.py
  python reports/build_b2b_weekly.py --deploy
"""
import argparse
import json
import shutil
from datetime import date, datetime
from pathlib import Path

from b2b_render import (badge, card, empty, esc, eur, kpi, name_list, note,
                        pct_change, rank_medal, section, slot, split_code,
                        table, trunc)
from b2b_style import CSS, CSS_WEEKLY

HERE = Path(__file__).resolve().parent

MOIS_FR = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
           "aout", "septembre", "octobre", "novembre", "decembre"]


def d_fr(iso):
    """2026-08-03 -> 03/08."""
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "&mdash;"


def d_fr_long(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {MOIS_FR[d.month - 1]} {d.year}"


def chan_tag(ch):
    return f'<span class="tag {slot(ch)}">{esc(ch)}</span>'


def week_bars(history, channels):
    """Barres empilees par canal, une ligne par semaine."""
    vmax = max([max(h["ca"], 0) for h in history] + [1])
    rows = []
    for h in history:
        segs = []
        for ch in channels:  # ordre fixe, jamais trie par valeur
            v = h["by_channel"].get(ch, 0)
            if v <= 0:
                continue
            segs.append(f'<span class="{slot(ch)}" style="width:{v / vmax * 100:.2f}%" '
                        f'title="{esc(ch)} — {eur(v)} €"></span>')
        cur = " today" if h.get("is_current") else ""
        rows.append(f"""
  <div class="hour-bar{cur}">
    <span class="hour-label">{esc(h["label"])} <span class="muted">{esc(h["range"])}</span>
      {'<em>semaine</em>' if cur else ''}</span>
    <span class="bar-track"><span class="bar" style="width:{max(h["ca"], 0) / vmax * 100:.2f}%">
      {''.join(segs)}</span></span>
    <span class="bar-value{' neg' if h["ca"] < 0 else ''}">{eur(h["ca"])} €</span>
    <span class="bar-count">{h["n"]} fact.</span>
  </div>""")
    legend = "".join(f'<span class="lg"><i class="{slot(c)}"></i>{esc(c)}</span>'
                     for c in channels)
    return f'<div class="legend">{legend}</div>' + "".join(rows)


def channel_split(by_channel, channels, total):
    """Barres simples : repartition d'un total par canal."""
    vmax = max(list(by_channel.values()) + [1])
    return "".join(f"""
  <div class="hour-bar">
    <span class="hour-label"><span class="dot {slot(c)}"></span>{esc(c)}</span>
    <span class="bar-track"><span class="bar" style="width:{
        max(by_channel.get(c, 0), 0) / vmax * 100:.2f}%">
      <span class="{slot(c)}" style="width:100%"></span></span></span>
    <span class="bar-value">{eur(by_channel.get(c, 0))} €</span>
    <span class="bar-count">{eur(by_channel.get(c, 0) / total * 100, 1) if total else "0,0"}%</span>
  </div>""" for c in channels)


def age_badge(days, warn=30, alert=90):
    if days is None:
        return '<span class="badge neutral">&mdash;</span>'
    cls = "down" if days >= alert else ("neutral" if days >= warn else "up")
    return f'<span class="badge {cls}">{days} j</span>'


# --------------------------------------------------------------------------

def lecture(d):
    """Le paragraphe de synthese en tete de page — genere depuis les chiffres."""
    sem, cmp_ = d["semaine"], d["comparaisons"]
    total = sem["total_ht"]
    ch = sem["by_channel"]
    lead_ch = max(d["channels"], key=lambda c: ch[c]["ca"])
    cmds = d["commandes"]
    carnet = cmds["total_ht"] - total

    bits = [
        f'<b>{eur(total)} € HT</b> factures sur {sem["nb_factures"]} pieces et '
        f'{sem["nb_clients"]} clients (panier {eur(sem["panier_moyen"])} €).',
        f'{esc(lead_ch)} porte la semaine avec {eur(ch[lead_ch]["ca"])} € '
        f'({eur(ch[lead_ch]["ca"] / total * 100, 0) if total else "0"} %).',
    ]
    if cmp_["delta_s1_pct"] is not None:
        sens = "au-dessus" if cmp_["delta_s1_pct"] >= 0 else "sous"
        bits.append(f'{eur(abs(cmp_["delta_s1_pct"]), 1)} % {sens} de S-1, '
                    f'mais {eur(abs(cmp_["delta_moy4_pct"] or 0), 1)} % '
                    f'{"au-dessus" if (cmp_["delta_moy4_pct"] or 0) >= 0 else "sous"} '
                    f'la moyenne des 4 dernieres semaines.')
    bits.append(f'Prise de commandes {eur(cmds["total_ht"])} € : le carnet se '
                f'{"remplit" if carnet >= 0 else "vide"} de {eur(abs(carnet))} €.')
    if d["nouveaux_clients"] or d["reactives"]:
        bits.append(f'{len(d["nouveaux_clients"])} nouveau(x) client(s) et '
                    f'{len(d["reactives"])} reactivation(s).')
    return f'<div class="lead">{" ".join(bits)}</div>'


def alertes(d):
    """Le bloc « a traiter » — uniquement ce qui demande une action."""
    items = []
    ytd = d["ytd"]
    if ytd.get("note"):
        c = ytd["comparable"]
        items.append(
            f'<b>Comparaison annuelle</b> — {esc(ytd["note"])} Sur base recalee : '
            f'{eur(c["ca"])} € vs {eur(c["ca_n_1"])} € en N-1, soit '
            f'{eur(c["delta_pct"], 1)} %.')
    dorm = d["dormants_total"]
    if dorm["nb"]:
        items.append(
            f'<b>{dorm["nb"]} clients dormants</b> (aucune facture depuis 60 jours '
            f'ou plus) representant {eur(dorm["ca_12m"])} € de CA sur 12 mois — '
            f'matiere premiere de la televente.')
    old_pipe = [p for p in d["pipeline"]["items"]
                if p["untaxed"] > 0 and (p.get("age_days") or 0) >= 30]
    if old_pipe:
        items.append(
            f'<b>{len(old_pipe)} devis de plus de 30 jours</b> encore ouverts '
            f'({eur(sum(p["untaxed"] for p in old_pipe))} €) : '
            f'{esc(name_list(old_pipe, 3))}.')
    old_dr = [x for x in d["drafts"]["items"] if x["untaxed"] > 0]
    if old_dr:
        items.append(
            f'<b>{len(old_dr)} facture(s) en brouillon chiffree(s)</b> pour '
            f'{eur(sum(x["untaxed"] for x in old_dr))} € — a poster ou a annuler : '
            f'{esc(name_list(old_dr, 3))}.')
    zero_dr = [x for x in d["drafts"]["items"] if x["untaxed"] == 0]
    if zero_dr:
        items.append(f'{len(zero_dr)} brouillon(s) vide(s) a nettoyer : '
                     f'{esc(name_list(zero_dr, 4))}.')
    if not items:
        return ""
    return ('<div class="alert"><strong>A traiter</strong><ul>'
            + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>")


def render(d):
    channels = d["channels"]
    sem, cmp_, w = d["semaine"], d["comparaisons"], d["week"]
    total = sem["total_ht"]
    gen = datetime.fromisoformat(d["generated_at"])

    # ---- KPI de la semaine ----
    kpis = "".join([
        kpi(f'{eur(total)} €', "CA HT facture"),
        kpi(str(sem["nb_factures"]), "Factures"),
        kpi(str(sem["nb_clients"]), "Clients actifs"),
        kpi(f'{eur(sem["panier_moyen"])} €', "Facture moy."),
        kpi(badge(cmp_["delta_s1_pct"]), "vs S-1"),
        kpi(badge(cmp_["delta_moy4_pct"]), "vs moy. 4 sem."),
        kpi(badge(cmp_["delta_n1_pct"]), "vs N-1"),
    ])

    # ---- Cartes canal ----
    ranked = sorted(channels, key=lambda c: -sem["by_channel"][c]["ca"])
    rank_cls = ["rank-first", "rank-second", "rank-third"]
    prev = cmp_["s_moins_1"]
    chan_cards = []
    for i, ch in enumerate(ranked):
        cell = sem["by_channel"][ch]
        v, n = cell["ca"], cell["n"]
        prev_v = prev["by_channel"].get(ch, 0) if prev else None
        ly_v = cmp_["n_1"]["by_channel"].get(ch, 0)
        chan_cards.append(f"""
<div class="chan-card {rank_cls[i]}">
  <div class="chan-header">
    <h2><span class="dot {slot(ch)}"></span>{esc(ch)}</h2>
    <span class="chan-rank r{i + 1}">#{i + 1} CA</span>
  </div>
  <div class="kpi-row">
    {kpi(f'{eur(v)} €', "CA HT")}
    {kpi(f'{eur(v / total * 100, 1) if total else "0,0"}%', "Part")}
    {kpi(str(n), "Factures")}
  </div>
  <div class="chan-foot">
    vs S-1 ({eur(prev_v) if prev else "—"} €) {badge(pct_change(v, prev_v))}
    &middot; vs N-1 ({eur(ly_v)} €) {badge(pct_change(v, ly_v))}
  </div>
</div>""")

    # ---- Prise de commandes ----
    cmds = d["commandes"]
    carnet = cmds["total_ht"] - total
    cmd_kpis = "".join([
        kpi(f'{eur(cmds["total_ht"])} €', "Commandes prises HT"),
        kpi(str(cmds["nb"]), "Commandes"),
        kpi(f'{eur(total)} €', "Facture HT", "flat"),
        kpi(f'{"+" if carnet >= 0 else "−"}{eur(abs(carnet))} €', "Effet carnet",
            "flat"),
    ])
    vendeurs_body = table(
        ["Vendeur", "Cdes", "Montant HT", "Part"], cmds["vendeurs"],
        [
            {"get": lambda r, i: esc(trunc(r["user"], 34))},
            {"cls": "right", "get": lambda r, i: str(r["n"])},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca"])} €</strong>'},
            {"cls": "right muted", "get": lambda r, i: (
                f'{eur(r["ca"] / cmds["total_ht"] * 100, 1)}%'
                if cmds["total_ht"] else "&mdash;")},
        ]) if cmds["vendeurs"] else empty("Aucune commande confirmee sur la semaine.")

    # ---- Top clients ----
    cl = d["top_clients"]
    clients_body = table(
        ["#", "Client", "Canal", "Fact.", "CA HT", "vs sa moy. hebdo"], cl,
        [
            {"cls": "medal", "get": lambda r, i: rank_medal(i)},
            {"get": lambda r, i: esc(trunc(r["partner"], 40))},
            {"get": lambda r, i: chan_tag(r["channel"])},
            {"cls": "right", "get": lambda r, i: str(r["n"])},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca"])} €</strong>'},
            {"cls": "right", "get": lambda r, i: badge(r["delta_pct"])},
        ]) if cl else empty("Aucune facture B2B sur la semaine.")

    # ---- Top produits ----
    pr = d["top_produits"]
    produits_body = table(
        ["#", "Produit", "Qte", "CA HT", "vs S-1"], pr,
        [
            {"cls": "medal", "get": lambda r, i: rank_medal(i)},
            {"get": lambda r, i: (
                f'<span class="sku">{esc(split_code(r["label"])[0])}</span> '
                if split_code(r["label"])[0] else "")
                + esc(trunc(split_code(r["label"])[1], 36))},
            {"cls": "right", "get": lambda r, i: eur(r["qty"], 0)},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca"])} €</strong>'},
            {"cls": "right", "get": lambda r, i: badge(r["delta_pct"])},
        ]) if pr else empty("Aucune ligne produit sur la semaine.")

    # ---- Mouvement de portefeuille ----
    mouv = ([{**c, "kind": "new"} for c in d["nouveaux_clients"]]
            + [{**c, "kind": "back"} for c in d["reactives"]])
    mouv.sort(key=lambda c: -c["ca"])
    mouv_body = table(
        ["Client", "Canal", "Statut", "Silence", "CA HT"], mouv,
        [
            {"get": lambda r, i: esc(trunc(r["partner"], 34))},
            {"get": lambda r, i: chan_tag(r["channel"])},
            {"get": lambda r, i: (
                '<span class="pill new">nouveau</span>' if r["kind"] == "new"
                else '<span class="pill back">reactive</span>')},
            {"cls": "right muted", "get": lambda r, i: (
                f'{r["gap_days"]} j' if r.get("gap_days") else "&mdash;")},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca"])} €</strong>'},
        ]) if mouv else empty("Aucun nouveau client ni reactivation cette semaine.")

    dorm = d["dormants"]
    dorm_body = (table(
        ["Client", "Canal", "Derniere fact.", "Silence", "CA 12 mois"], dorm,
        [
            {"get": lambda r, i: esc(trunc(r["partner"], 32))},
            {"get": lambda r, i: chan_tag(r["channel"])},
            {"cls": "right mono", "get": lambda r, i: d_fr(r["last_seen"])},
            {"cls": "right", "get": lambda r, i: age_badge(r["gap_days"], 60, 120)},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca_12m"])} €</strong>'},
        ]) if dorm else empty("Aucun client dormant.")) + note(
        f'{d["dormants_total"]["nb"]} clients dormants au total pour '
        f'{eur(d["dormants_total"]["ca_12m"])} € de CA 12 mois — les 20 premiers '
        f'sont affiches. Un compte peut etre une adresse de facturation centrale '
        f'(ex. une comptabilite fournisseurs) et non un point de vente : verifier '
        f'avant de relancer.')

    # ---- Cumuls ----
    mtd, ytd = d["mtd"], d["ytd"]
    mtd_body = channel_split(mtd["by_channel"], channels, mtd["total_ht"])
    ytd_body = channel_split(ytd["by_channel"], channels, ytd["total_ht"])
    cmpb = ytd.get("comparable")
    ytd_foot = note(
        f'{ytd["note"]} Sur base recalee : {eur(cmpb["ca"])} € contre '
        f'{eur(cmpb["ca_n_1"])} € en N-1 ({eur(cmpb["delta_pct"], 1)} %).'
        if ytd.get("note") and cmpb else
        f'N-1 sur la meme periode : {eur(ytd["n_1"])} € '
        f'({eur(ytd["delta_pct"], 1) if ytd["delta_pct"] is not None else "—"} %).')

    # ---- Pipeline / brouillons ----
    pipe = d["pipeline"]
    pipe_items = [p for p in pipe["items"] if p["untaxed"] > 0]
    pipe_zero = len(pipe["items"]) - len(pipe_items)
    pipe_body = (table(
        ["Devis", "Client", "Canal", "Age", "Montant HT"], pipe_items,
        [
            {"cls": "mono", "get": lambda r, i: esc(r["name"])},
            {"get": lambda r, i: esc(trunc(r["partner"], 30))},
            {"get": lambda r, i: chan_tag(r["channel"])},
            {"cls": "right", "get": lambda r, i: age_badge(r.get("age_days"))},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["untaxed"])} €</strong>'},
        ]) if pipe_items else empty("Aucun devis B2B chiffre en attente.")) \
        + note(f"{pipe_zero} devis a 0,00 € masque(s)." if pipe_zero else None)

    dr = d["drafts"]
    dr_items = [x for x in dr["items"] if x["untaxed"] > 0]
    dr_zero = [x for x in dr["items"] if x["untaxed"] == 0]
    drafts_body = (table(
        ["Client", "Canal", "Date", "Montant HT"], dr_items,
        [
            {"get": lambda r, i: esc(trunc(r["partner"], 32))},
            {"get": lambda r, i: chan_tag(r["channel"])},
            {"cls": "right mono", "get": lambda r, i: d_fr(r["date"])},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["untaxed"])} €</strong>'},
        ]) if dr_items else empty("Aucun brouillon chiffre en attente.")) \
        + note(f"{len(dr_zero)} brouillon(s) a 0,00 € : {name_list(dr_zero)}."
               if dr_zero else None)

    # ---- Detail factures ----
    facts = sem["factures"]
    shown = [f for f in facts if f["untaxed"] != 0]
    zeros = [f for f in facts if f["untaxed"] == 0]
    detail_body = (table(
        ["Piece", "Date", "Client", "Canal", "Origine", "HT"], shown,
        [
            {"cls": "mono", "get": lambda r, i: esc(r["name"])},
            {"cls": "mono muted", "get": lambda r, i: d_fr(r["date"])},
            {"get": lambda r, i: esc(trunc(r["partner"], 38))},
            {"get": lambda r, i: chan_tag(r["channel"])},
            {"cls": "mono muted", "get": lambda r, i: esc(r["origin"]) or "&mdash;"},
            {"cls": "right", "get": lambda r, i: (
                f'<strong class="neg">{eur(r["untaxed"])} €</strong>' if r["untaxed"] < 0
                else f'<strong>{eur(r["untaxed"])} €</strong>')},
        ]) if shown else empty("Aucune facture B2B sur la semaine.")) \
        + note(f'{len(zeros)} facture(s) a 0,00 € masquee(s) : {name_list(zeros)}.'
               if zeros else None)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>B2B Weekly Review — Teatower — {esc(w["iso"])}</title>
<style>
{CSS}
{CSS_WEEKLY}
</style>
</head>
<body>

<header>
  <h1>B2B Weekly Review &mdash; Teatower</h1>
  <div class="meta">
    <div><strong>{esc(w["iso"])}</strong> &middot; du {d_fr_long(w["monday"])}
      au {d_fr_long(w["sunday"])}</div>
    <div>G&eacute;n&eacute;r&eacute; le {gen.strftime("%Y-%m-%d %H:%M")} &middot;
      <a href="../">dashboard quotidien</a></div>
  </div>
</header>

{lecture(d)}
{alertes(d)}

{section(f'Semaine {esc(w["iso"])}')}
<div class="kpi-row">{kpis}</div>

{section("Par canal — GMS / Horeca / Revendeurs")}
<div class="grid three">{''.join(chan_cards)}</div>

{section("Cinq dernieres semaines")}
<div class="grid full">
  {card("Chiffre d'affaires HT facture par semaine", week_bars(d["historique"], channels))}
</div>

{section("Prise de commandes de la semaine")}
<div class="kpi-row">{cmd_kpis}</div>
<div class="grid">
  {card("Commandes confirmees par canal",
        channel_split(cmds["by_channel"], channels, cmds["total_ht"]))}
  {card("Par vendeur", vendeurs_body)}
</div>

{section("Top de la semaine")}
<div class="grid">
  {card("Top clients", clients_body)}
  {card("Top produits", produits_body)}
</div>

{section("Mouvement de portefeuille")}
<div class="grid">
  {card("Nouveaux clients et reactivations", mouv_body)}
  {card("Clients dormants — top 20 par CA 12 mois", dorm_body)}
</div>

{section("Cumuls")}
<div class="grid">
  {card(f'Mois en cours — {eur(mtd["total_ht"])} € HT · {mtd["nb_factures"]} factures',
        mtd_body)}
  {card(f'Annee en cours — {eur(ytd["total_ht"])} € HT · {ytd["nb_factures"]} factures',
        ytd_body + ytd_foot)}
</div>

{section("En attente")}
<div class="grid">
  {card(f'Pipeline devis — {pipe["nb"]} / {eur(pipe["total_ht"])} €', pipe_body)}
  {card(f'Factures en brouillon — {dr["nb"]} / {eur(dr["total_ht"])} €', drafts_body)}
</div>

{section("Detail des factures de la semaine")}
<div class="grid full">
  {card(f'{len(shown)} facture(s)', detail_body)}
</div>

<footer>
  Source Odoo (tea-tree). Montants HT, avoirs comptes en negatif.
  Segmentation par tag client GMS / Horeca / Revendeurs ; un client sans tag
  n'est pas compte comme B2B.
</footer>

</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "b2b_weekly_data.json"))
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--deploy-dir", default=str(HERE / "b2b-dashboard-deploy" / "weekly"))
    ap.add_argument("--archive-dir", default=str(HERE))
    args = ap.parse_args()

    data_path = Path(args.data)
    d = json.loads(data_path.read_text(encoding="utf-8"))
    page = render(d)

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f'b2b_weekly_review_{d["week"]["iso"]}.html'
    archive.write_text(page, encoding="utf-8")
    print(f"OK  {archive}")

    if args.deploy:
        dd = Path(args.deploy_dir)
        dd.mkdir(parents=True, exist_ok=True)
        (dd / "index.html").write_text(page, encoding="utf-8")
        print(f"OK  {dd / 'index.html'}")
        target = dd / "data.json"
        # En CI l'extraction ecrit deja dans le dossier de deploiement : copier
        # le fichier sur lui-meme leverait SameFileError.
        if data_path.resolve() != target.resolve():
            shutil.copyfile(data_path, target)
            print(f"OK  {target}")


if __name__ == "__main__":
    main()
