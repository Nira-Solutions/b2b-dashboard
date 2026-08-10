"""
b2b_weekly_extract.py — Extraction Odoo pour le B2B Weekly Review Teatower.

Meme convention de segmentation que `b2b_dashboard_extract.py` (tags
res.partner.category : GMS 88/27, Horeca 84/26, Revendeurs 85 ; priorite
GMS > Horeca > Revendeurs ; un partenaire sans tag n'est PAS B2B).

Produit `reports/b2b_weekly_data.json` : la photo B2B de la semaine ecoulee
(lundi -> dimanche), avec :
  - CA HT facture par canal + comparaison S-1..S-4 et meme semaine N-1
  - prise de commandes (sale.order confirmees) vs facturation
  - top clients / top produits, et pour chaque client le delta vs sa moyenne
  - nouveaux clients B2B (1ere facture de leur histoire)
  - clients reactives (rien depuis >=60j avant cette semaine)
  - clients dormants a relancer (actifs sur 12 mois, muets depuis >=60j)
  - MTD + YTD, drafts de factures et pipeline devis

Usage :
  python reports/b2b_weekly_extract.py                    # derniere semaine complete
  python reports/b2b_weekly_extract.py --week 2026-08-03  # semaine du lundi donne
  python reports/b2b_weekly_extract.py --out chemin.json

Credentials : ODOO_PWD dans l'environnement.
"""
import argparse
import json
import os
import sys
import xmlrpc.client
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

URL = "https://tea-tree.odoo.com"
DB = "tsc-be-tea-tree-main-18515272"
USER = "nicolas.raes@teatower.com"

CHANNELS = [
    ("GMS", [88, 27]),
    ("Horeca", [84, 26]),
    ("Revendeurs", [85]),
]
CHANNEL_ORDER = [c[0] for c in CHANNELS]

TOP_N_CLIENTS = 15
TOP_N_PRODUITS = 15
HISTORY_WEEKS = 4        # nb de semaines precedentes pour la moyenne mobile
DORMANT_DAYS = 60        # seuil de silence pour "dormant" / "reactive"

MOIS_FR = ["janvier", "fevrier", "mars", "avril", "mai", "juin",
           "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]


def connect():
    pwd = os.environ.get("ODOO_PWD")
    if not pwd:
        raise SystemExit("Definir ODOO_PWD avant d'executer ce script.")
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, pwd, {})
    if not uid:
        raise SystemExit("Authentification Odoo refusee — verifier ODOO_PWD.")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    def call(model, method, args, kw=None):
        return models.execute_kw(DB, uid, pwd, model, method, args, kw or {})

    return call


def channel_of(cats):
    for name, tag_ids in CHANNELS:
        if any(c in tag_ids for c in cats):
            return name
    return None


def fetch_invoices(call, date_from, date_to):
    domain = [
        ("move_type", "in", ["out_invoice", "out_refund"]),
        ("state", "=", "posted"),
        ("invoice_date", ">=", date_from.isoformat()),
        ("invoice_date", "<=", date_to.isoformat()),
    ]
    return call("account.move", "search_read", [domain], {
        "fields": ["id", "name", "move_type", "invoice_date", "partner_id",
                   "amount_untaxed", "amount_total", "invoice_origin"],
    })


def partner_channels(call, partner_ids):
    """{partner_id: (canal|None, nom societe, commercial_partner_id)}."""
    if not partner_ids:
        return {}
    partners = call("res.partner", "read", [list(partner_ids)],
                    {"fields": ["id", "name", "category_id", "parent_id",
                                "commercial_partner_id"]})
    by_id = {p["id"]: p for p in partners}
    extra_ids = set()
    for p in partners:
        cp = p.get("commercial_partner_id")
        if cp and cp[0] not in by_id:
            extra_ids.add(cp[0])
    if extra_ids:
        for p in call("res.partner", "read", [sorted(extra_ids)],
                      {"fields": ["id", "name", "category_id"]}):
            by_id[p["id"]] = p

    out = {}
    for pid in partner_ids:
        p = by_id.get(pid)
        if not p:
            out[pid] = (None, f"#{pid}", pid)
            continue
        ch = channel_of(p.get("category_id") or [])
        cp = p.get("commercial_partner_id")
        cp_id = cp[0] if cp else pid
        if ch is None and cp and cp[0] in by_id:
            ch = channel_of(by_id[cp[0]].get("category_id") or [])
        label = by_id[cp_id]["name"] if cp_id in by_id else p["name"]
        out[pid] = (ch, label, cp_id)
    return out


def b2b_lines(invoices, pmap):
    rows = []
    for inv in invoices:
        if not inv.get("partner_id"):
            continue
        pid = inv["partner_id"][0]
        ch, label, cp_id = pmap.get(pid, (None, inv["partner_id"][1], pid))
        if ch is None:
            continue
        sign = -1 if inv["move_type"] == "out_refund" else 1
        rows.append({
            "id": inv["id"],
            "name": inv["name"],
            "date": inv["invoice_date"],
            "channel": ch,
            "partner_id": cp_id,
            "partner": label,
            "untaxed": round(inv["amount_untaxed"] * sign, 2),
            "total": round(inv["amount_total"] * sign, 2),
            "origin": inv.get("invoice_origin") or "",
            "is_refund": inv["move_type"] == "out_refund",
        })
    return rows


def top_products(call, invoice_ids, limit=TOP_N_PRODUITS):
    if not invoice_ids:
        return []
    lines = call("account.move.line", "search_read", [[
        ("move_id", "in", invoice_ids),
        ("display_type", "=", "product"),
        ("product_id", "!=", False),
    ]], {"fields": ["product_id", "quantity", "price_subtotal", "move_id"]})
    refunds = set()
    if lines:
        moves = call("account.move", "read", [sorted({l["move_id"][0] for l in lines})],
                     {"fields": ["id", "move_type"]})
        refunds = {m["id"] for m in moves if m["move_type"] == "out_refund"}
    agg = defaultdict(lambda: {"qty": 0.0, "ca": 0.0, "name": ""})
    for l in lines:
        sign = -1 if l["move_id"][0] in refunds else 1
        pid, pname = l["product_id"]
        a = agg[pid]
        a["qty"] += l["quantity"] * sign
        a["ca"] += l["price_subtotal"] * sign
        a["name"] = pname
    out = [{"product_id": k, "label": v["name"],
            "qty": round(v["qty"], 2), "ca": round(v["ca"], 2)}
           for k, v in agg.items()]
    out.sort(key=lambda x: -x["ca"])
    return out[:limit]


def agg_by_channel(rows):
    d = {c: {"ca": 0.0, "n": 0} for c in CHANNEL_ORDER}
    for r in rows:
        d[r["channel"]]["ca"] += r["untaxed"]
        d[r["channel"]]["n"] += 1
    for v in d.values():
        v["ca"] = round(v["ca"], 2)
    return d


def pct(new, old):
    if not old:
        return None
    return round((new - old) / abs(old) * 100, 1)


def fr_date(d):
    return f"{d.day:02d}/{d.month:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="Lundi de la semaine analysee (YYYY-MM-DD). "
                                   "Defaut : derniere semaine complete.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    today = date.today()
    if args.week:
        monday = date.fromisoformat(args.week)
        monday -= timedelta(days=monday.weekday())
    else:
        monday = today - timedelta(days=today.weekday() + 7)
    sunday = monday + timedelta(days=6)
    iso_year, iso_week, _ = monday.isocalendar()

    out_path = Path(args.out) if args.out else Path(__file__).with_name("b2b_weekly_data.json")

    call = connect()
    partner_cache = {}

    def call_partners(pids):
        missing = [p for p in pids if p not in partner_cache]
        if missing:
            partner_cache.update(partner_channels(call, missing))
        return {p: partner_cache[p] for p in pids if p in partner_cache}

    def week_rows(m, s):
        inv = fetch_invoices(call, m, s)
        pm = call_partners({i["partner_id"][0] for i in inv if i.get("partner_id")})
        return b2b_lines(inv, pm)

    # --- Semaine cible -----------------------------------------------------
    rows = week_rows(monday, sunday)
    by_channel = agg_by_channel(rows)
    total = round(sum(v["ca"] for v in by_channel.values()), 2)

    # --- Semaines precedentes ---------------------------------------------
    history = []
    for k in range(HISTORY_WEEKS, 0, -1):
        m = monday - timedelta(days=7 * k)
        s = m + timedelta(days=6)
        rk = week_rows(m, s)
        ck = agg_by_channel(rk)
        history.append({
            "monday": m.isoformat(),
            "label": f"S{m.isocalendar()[1]}",
            "range": f"{fr_date(m)}-{fr_date(s)}",
            "ca": round(sum(v["ca"] for v in ck.values()), 2),
            "n": len(rk),
            "by_channel": {k2: v["ca"] for k2, v in ck.items()},
        })
    history.append({
        "monday": monday.isoformat(),
        "label": f"S{iso_week}",
        "range": f"{fr_date(monday)}-{fr_date(sunday)}",
        "ca": total, "n": len(rows),
        "by_channel": {k2: v["ca"] for k2, v in by_channel.items()},
        "is_current": True,
    })

    prev = history[-2] if len(history) >= 2 else None
    hist_ca = [h["ca"] for h in history[:-1]]
    moy4 = round(sum(hist_ca) / len(hist_ca), 2) if hist_ca else 0.0

    # --- Meme semaine N-1 --------------------------------------------------
    try:
        m_ly = date.fromisocalendar(iso_year - 1, iso_week, 1)
    except ValueError:
        m_ly = monday - timedelta(days=364)
    s_ly = m_ly + timedelta(days=6)
    rows_ly = week_rows(m_ly, s_ly)
    ch_ly = agg_by_channel(rows_ly)
    total_ly = round(sum(v["ca"] for v in ch_ly.values()), 2)

    # --- Clients de la semaine --------------------------------------------
    by_client = defaultdict(lambda: {"ca": 0.0, "n": 0, "channel": "", "pid": 0})
    for r in rows:
        c = by_client[r["partner"]]
        c["ca"] += r["untaxed"]
        c["n"] += 1
        c["channel"] = r["channel"]
        c["pid"] = r["partner_id"]
    clients = [{"partner": k, "ca": round(v["ca"], 2), "n": v["n"],
                "channel": v["channel"], "partner_id": v["pid"]}
               for k, v in by_client.items()]
    clients.sort(key=lambda x: -x["ca"])

    # --- Historique 12 mois par client (nouveaux / reactives / dormants) ---
    hist_start = monday - timedelta(days=365)
    inv_hist = fetch_invoices(call, hist_start, monday - timedelta(days=1))
    pm_hist = call_partners({i["partner_id"][0] for i in inv_hist if i.get("partner_id")})
    rows_hist = b2b_lines(inv_hist, pm_hist)

    last_seen = {}      # partner_id -> derniere date facture avant la semaine
    ca_12m = defaultdict(float)
    n_12m = defaultdict(int)
    name_of = {}
    chan_of = {}
    for r in rows_hist:
        pid = r["partner_id"]
        ca_12m[pid] += r["untaxed"]
        n_12m[pid] += 1
        name_of[pid] = r["partner"]
        chan_of[pid] = r["channel"]
        if pid not in last_seen or r["date"] > last_seen[pid]:
            last_seen[pid] = r["date"]

    # Antecedents complets (pour distinguer "nouveau" de "reactive")
    ever_ids = set(last_seen)
    older = call("account.move", "search_read", [[
        ("move_type", "in", ["out_invoice", "out_refund"]),
        ("state", "=", "posted"),
        ("invoice_date", "<", hist_start.isoformat()),
    ]], {"fields": ["partner_id"]})
    pm_old = call_partners({o["partner_id"][0] for o in older if o.get("partner_id")})
    for o in older:
        if not o.get("partner_id"):
            continue
        ch, _label, cp_id = pm_old.get(o["partner_id"][0], (None, "", 0))
        if ch is not None:
            ever_ids.add(cp_id)

    nouveaux, reactives = [], []
    for c in clients:
        pid = c["partner_id"]
        if pid not in ever_ids:
            nouveaux.append(c)
        elif pid in last_seen:
            gap = (monday - date.fromisoformat(last_seen[pid])).days
            if gap >= DORMANT_DAYS:
                reactives.append({**c, "last_seen": last_seen[pid], "gap_days": gap})
        else:
            reactives.append({**c, "last_seen": None, "gap_days": None})

    week_pids = {c["partner_id"] for c in clients}
    dormants = []
    for pid, seen in last_seen.items():
        if pid in week_pids:
            continue
        gap = (sunday - date.fromisoformat(seen)).days
        if gap >= DORMANT_DAYS and ca_12m[pid] > 0:
            dormants.append({"partner": name_of[pid], "partner_id": pid,
                             "channel": chan_of[pid], "last_seen": seen,
                             "gap_days": gap, "ca_12m": round(ca_12m[pid], 2),
                             "n_12m": n_12m[pid]})
    dormants.sort(key=lambda d: -d["ca_12m"])

    # Delta client vs sa moyenne hebdo 12 mois
    for c in clients:
        base = ca_12m.get(c["partner_id"], 0.0) / 52.0
        c["ca_hebdo_moyen_12m"] = round(base, 2)
        c["delta_pct"] = pct(c["ca"], base) if base else None

    # --- Produits ----------------------------------------------------------
    produits = top_products(call, [r["id"] for r in rows])
    produits_prev = top_products(call, [r["id"] for r in week_rows(
        monday - timedelta(days=7), monday - timedelta(days=1))], limit=100)
    prev_ca = {p["product_id"]: p["ca"] for p in produits_prev}
    for p in produits:
        p["ca_prev"] = round(prev_ca.get(p["product_id"], 0.0), 2)
        p["delta_pct"] = pct(p["ca"], p["ca_prev"])

    # --- Prise de commandes (sale.order confirmees dans la semaine) --------
    so = call("sale.order", "search_read", [[
        ("state", "in", ["sale", "done"]),
        ("date_order", ">=", monday.isoformat() + " 00:00:00"),
        ("date_order", "<=", sunday.isoformat() + " 23:59:59"),
    ]], {"fields": ["id", "name", "partner_id", "amount_untaxed", "date_order",
                    "user_id", "state"]})
    pm_so = call_partners({s["partner_id"][0] for s in so if s.get("partner_id")})
    so_rows = []
    for s in so:
        if not s.get("partner_id"):
            continue
        ch, label, cp_id = pm_so.get(s["partner_id"][0], (None, "", 0))
        if ch is None:
            continue
        so_rows.append({"name": s["name"], "partner": label, "channel": ch,
                        "untaxed": round(s["amount_untaxed"], 2),
                        "date": (s.get("date_order") or "")[:10],
                        "user": (s.get("user_id") or [None, ""])[1]})
    so_by_channel = {c: 0.0 for c in CHANNEL_ORDER}
    so_by_user = defaultdict(lambda: {"ca": 0.0, "n": 0})
    for s in so_rows:
        so_by_channel[s["channel"]] += s["untaxed"]
        u = so_by_user[s["user"] or "(sans vendeur)"]
        u["ca"] += s["untaxed"]
        u["n"] += 1
    so_by_channel = {k: round(v, 2) for k, v in so_by_channel.items()}
    vendeurs = [{"user": k, "ca": round(v["ca"], 2), "n": v["n"]}
                for k, v in so_by_user.items()]
    vendeurs.sort(key=lambda x: -x["ca"])

    # --- MTD / YTD ---------------------------------------------------------
    mtd_start = sunday.replace(day=1)
    rows_mtd = week_rows(mtd_start, sunday) if mtd_start <= sunday else []
    mtd = agg_by_channel(rows_mtd)

    ytd_start = date(sunday.year, 1, 1)
    rows_ytd = week_rows(ytd_start, sunday)
    ytd = agg_by_channel(rows_ytd)
    sunday_ly = sunday.replace(year=sunday.year - 1)
    rows_ytd_ly = week_rows(date(sunday.year - 1, 1, 1), sunday_ly)
    ytd_ly = agg_by_channel(rows_ytd_ly)

    # La base Odoo ne remonte pas au 1er janvier N-1 (reprise de donnees) : un
    # YTD-vs-YTD brut surestime alors mecaniquement la croissance. On recale les
    # deux periodes sur le 1er mois reellement alimente en N-1.
    ytd_note = None
    comparable = None
    if rows_ytd_ly:
        first_ly = min(r["date"] for r in rows_ytd_ly)
        cmp_start_ly = date.fromisoformat(first_ly).replace(day=1)
        if cmp_start_ly > date(sunday.year - 1, 1, 1):
            cmp_start = cmp_start_ly.replace(year=sunday.year)
            a = sum(v["ca"] for v in agg_by_channel(
                [r for r in rows_ytd if r["date"] >= cmp_start.isoformat()]).values())
            b = sum(v["ca"] for v in agg_by_channel(
                [r for r in rows_ytd_ly if r["date"] >= cmp_start_ly.isoformat()]).values())
            comparable = {"depuis": cmp_start.isoformat(), "depuis_n_1": cmp_start_ly.isoformat(),
                          "ca": round(a, 2), "ca_n_1": round(b, 2), "delta_pct": pct(a, b)}
            ytd_note = (f"Aucune facture B2B en base avant {first_ly} : le YTD N-1 est "
                        f"tronque, le delta brut n'est pas exploitable. Utiliser la "
                        f"comparaison recalee depuis {cmp_start_ly.strftime('%m/%Y')}.")

    # --- Drafts + pipeline -------------------------------------------------
    drafts_raw = call("account.move", "search_read", [[
        ("move_type", "in", ["out_invoice", "out_refund"]),
        ("state", "=", "draft"),
    ]], {"fields": ["id", "name", "partner_id", "amount_untaxed", "invoice_date",
                    "create_date"]})
    pm_d = call_partners({d["partner_id"][0] for d in drafts_raw if d.get("partner_id")})
    drafts = []
    for d in drafts_raw:
        if not d.get("partner_id"):
            continue
        ch, label, _ = pm_d.get(d["partner_id"][0], (None, "", 0))
        if ch is None:
            continue
        nm = d.get("name") or ""
        drafts.append({"name": nm if nm not in ("", "/", "False") else "(brouillon)",
                       "partner": label, "channel": ch,
                       "untaxed": round(d["amount_untaxed"], 2),
                       "date": d.get("invoice_date") or (d.get("create_date") or "")[:10]})
    drafts.sort(key=lambda r: -r["untaxed"])

    quotes = call("sale.order", "search_read", [[("state", "in", ["draft", "sent"])]],
                  {"fields": ["id", "name", "partner_id", "amount_untaxed",
                              "date_order", "state", "user_id"]})
    pm_q = call_partners({q["partner_id"][0] for q in quotes if q.get("partner_id")})
    pipeline = []
    for q in quotes:
        if not q.get("partner_id"):
            continue
        ch, label, _ = pm_q.get(q["partner_id"][0], (None, "", 0))
        if ch is None:
            continue
        dd = (q.get("date_order") or "")[:10]
        age = (today - date.fromisoformat(dd)).days if dd else None
        pipeline.append({"name": q["name"], "partner": label, "channel": ch,
                         "untaxed": round(q["amount_untaxed"], 2), "date": dd,
                         "state": q["state"], "age_days": age,
                         "user": (q.get("user_id") or [None, ""])[1]})
    pipeline.sort(key=lambda r: -r["untaxed"])

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "week": {
            "iso": f"{iso_year}-S{iso_week:02d}",
            "num": iso_week,
            "monday": monday.isoformat(),
            "sunday": sunday.isoformat(),
            "label": f"S{iso_week} — du {monday.day} au {sunday.day} "
                     f"{MOIS_FR[sunday.month - 1]} {sunday.year}",
        },
        "channels": CHANNEL_ORDER,
        "semaine": {
            "total_ht": total,
            "nb_factures": len(rows),
            "nb_clients": len(clients),
            "panier_moyen": round(total / len(rows), 2) if rows else 0.0,
            "by_channel": by_channel,
            "factures": sorted(rows, key=lambda r: -r["untaxed"]),
        },
        "comparaisons": {
            "s_moins_1": prev,
            "delta_s1_pct": pct(total, prev["ca"]) if prev else None,
            "moyenne_4s": moy4,
            "delta_moy4_pct": pct(total, moy4),
            "n_1": {"monday": m_ly.isoformat(), "range": f"{fr_date(m_ly)}-{fr_date(s_ly)}",
                    "ca": total_ly, "n": len(rows_ly),
                    "by_channel": {k: v["ca"] for k, v in ch_ly.items()}},
            "delta_n1_pct": pct(total, total_ly),
        },
        "historique": history,
        "top_clients": clients[:TOP_N_CLIENTS],
        "top_produits": produits,
        "nouveaux_clients": nouveaux,
        "reactives": sorted(reactives, key=lambda c: -c["ca"]),
        "dormants": dormants[:20],
        "dormants_total": {"nb": len(dormants),
                           "ca_12m": round(sum(d["ca_12m"] for d in dormants), 2)},
        "commandes": {
            "nb": len(so_rows),
            "total_ht": round(sum(s["untaxed"] for s in so_rows), 2),
            "by_channel": so_by_channel,
            "vendeurs": vendeurs,
            "items": sorted(so_rows, key=lambda s: -s["untaxed"])[:20],
        },
        "mtd": {"depuis": mtd_start.isoformat(),
                "total_ht": round(sum(v["ca"] for v in mtd.values()), 2),
                "by_channel": {k: v["ca"] for k, v in mtd.items()},
                "nb_factures": len(rows_mtd)},
        "ytd": {"total_ht": round(sum(v["ca"] for v in ytd.values()), 2),
                "by_channel": {k: v["ca"] for k, v in ytd.items()},
                "nb_factures": len(rows_ytd),
                "n_1": round(sum(v["ca"] for v in ytd_ly.values()), 2),
                "delta_pct": pct(sum(v["ca"] for v in ytd.values()),
                                 sum(v["ca"] for v in ytd_ly.values())),
                "note": ytd_note,
                "comparable": comparable},
        "drafts": {"nb": len(drafts),
                   "total_ht": round(sum(d["untaxed"] for d in drafts), 2),
                   "items": drafts[:15]},
        "pipeline": {"nb": len(pipeline),
                     "total_ht": round(sum(p["untaxed"] for p in pipeline), 2),
                     "items": pipeline[:15]},
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def eur(x):
        return f"{x:,.2f}".replace(",", " ")

    print(f"OK  {out_path}")
    print(f"    {data['week']['label']}")
    print(f"    CA B2B facture : {eur(total)} EUR HT / {len(rows)} factures / "
          f"{len(clients)} clients")
    for c in CHANNEL_ORDER:
        v = by_channel[c]
        print(f"      {c:<12} {eur(v['ca']):>12} EUR  ({v['n']} fact.)")
    if prev:
        print(f"    vs S-1 ({prev['range']}) {eur(prev['ca'])} : "
              f"{data['comparaisons']['delta_s1_pct']} %")
    print(f"    vs moyenne 4S {eur(moy4)} : {data['comparaisons']['delta_moy4_pct']} %")
    print(f"    vs N-1 ({fr_date(m_ly)}-{fr_date(s_ly)}) {eur(total_ly)} : "
          f"{data['comparaisons']['delta_n1_pct']} %")
    print(f"    Commandes prises : {eur(data['commandes']['total_ht'])} EUR "
          f"({data['commandes']['nb']} SO)")
    print(f"    Nouveaux {len(nouveaux)} / Reactives {len(reactives)} / "
          f"Dormants {len(dormants)}")
    print(f"    MTD {eur(data['mtd']['total_ht'])} — YTD {eur(data['ytd']['total_ht'])}")
    if comparable:
        print(f"    YTD recale depuis {comparable['depuis_n_1'][:7]} : "
              f"{eur(comparable['ca'])} vs {eur(comparable['ca_n_1'])} "
              f"({comparable['delta_pct']} %)")
        print(f"    /!\\ {ytd_note}")
    else:
        print(f"    YTD vs N-1 : {data['ytd']['delta_pct']} %")
    print(f"    Drafts {data['drafts']['nb']} ({eur(data['drafts']['total_ht'])}) / "
          f"Pipeline {data['pipeline']['nb']} ({eur(data['pipeline']['total_ht'])})")


if __name__ == "__main__":
    sys.exit(main())
