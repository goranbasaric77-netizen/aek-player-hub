"""
player_hub_feed.py: most iz AEK GPS 2.5 u AEK Player Hub (Google tabela preko Apps Script-a).

Sve sto igrac vidi u hub-u dolazi odavde i iz GPS 2.5 motora, isto kao Daily Player Plan PDF (gym_dpp.py):
  - plan dana po igracu iz data/plan_kompletan_W<N>.csv (isti izbor reda kao DPP: gym_dpp._plan_red / _ciljevi)
  - vreme treninga/utakmice i protivnik iz data/mikrociklus_W<N>.csv (napomena reda), AM/PM kad sat nije upisan
  - gym program iz data/gym/gym_state.json (sesija igraca za taj dan, sa zamenama po kodovima, kg iz 1RM),
    aktivacija i mobility iz blokova iste sesije
  - referenca = SOPSTVENA UTAKMICA per 90 (data/mec_referenca.csv, kao Sidro); nedelje = x utakmice, plan nedelje iz motora;
    max brzina = max(max_velocity_baza, GPS sezona)
  - dani od poslednje brzinske ekspozicije (>= 95 %) i poslednja brzina iz data/brzina_dnevnik.csv
  - minuti poslednjeg meca iz data/mec_nastupi.csv
  - rezultat dana iz data/dnevni_niz.csv (zbir svih sesija tog dana: trening + mec + top-up), max brzina dana
  - dan meca: PRE uvoza meca svi dobijaju MATCH red (sastav se ne otkriva); POSLE uvoza ko je igrao 45+ ostaje
    na MATCH redu, ostali dobijaju top-up red i svoj rezultat
  - status igraca (data/status_igraca.csv: POVREDA, REHAB, BOLEST...) -> "Out of the team plan" + EN tekst
  - fokus dana iz data/hub_focus.csv (date,player,text; "*" za sve) ili --focus
  - nedelja igraca (tab Week) i sledeci mec iz mikrociklusa + plan_kompletan, u koloni extra_json

Pokretanje (iz AEK HUB launchera, dugme "POSALJI PLAN U PLAYER HUB", ili rucno):
  python player_hub_feed.py --date 2026-11-05 --url "https://script.google.com/macros/s/.../exec" --key <staff PIN>
  python player_hub_feed.py --date 2026-11-05 --dry-run        (samo upise hub_feed_<datum>.json, nista ne salje)

Posle treninga, kad se Catapult izvoz uveze u GPS 2.5, pokrenuti isto: tada salje i Results, a na dan meca
prebacuje igrace bez 45 min na top-up red.
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.normpath(os.path.join(HERE, "..", "..", "AEK_GPS_APP", "AEK_GPS_APP_DEMO", "data"))

# GPS ime (W1_baza_kamp.csv) -> id u hub-u (ROSTER u index.html)
NAME_TO_ID = {
    "Abubakary Koita": "koita", "Argyris Argyriou": "argyriou", "Barnabas Varga": "varga", "Christos Alexiou": "alexiou",
    "Dereck Kutesa": "kutesa", "Dimitris Kaloskamis": "kaloskamis", "Domagoj Vida": "vida", "Felipe Relvas": "relvas",
    "Hakim Sahabo": "sahabo", "Harold Moukoudi": "moukoudi", "Kaan Kairinen": "kairinen", "Kervin Ariaga": "ariaga",
    "Lazaros Rota": "rota", "Lovro Majer": "majer", "Luka Jovic": "jovic", "Martin Georgiev": "georgiev",
    "Mijat Gacinovic": "gacinovic", "Milan Vitalis": "vitalis", "Mpampis Likogiannis": "likogiannis",
    "Oleksandr Zubkov": "zubkov", "Petros Mantalos": "mantalos", "Razvan Marin": "marin", "Salvador Zine": "zine",
    "Spiros Christakopoulos": "christakopoulos", "Stavros Pilios": "pilios", "Joao Mario": "joaomario",
}
MODE_LABEL = {
    "COMPENSATION": "Compensation", "RECOVERY": "Recovery day", "ACTIVE RECOVERY": "Active recovery",
    "RECOVERY + TACTICAL": "Recovery + tactical", "SPEED": "Speed day", "TACTICAL": "Tactical session",
    "PRE-MATCH": "Match prep", "PRE-MATCH (PRATE EKIPU)": "Match prep", "MATCH": "Match day", "OFF": "Day off",
    "POST-MATCH TOP-UP": "Post-match top-up", "INDIVIDUALNO (SPATA)": "Individual session",
    "MD-4 (SPATA)": "Training", "MD-3 (SPATA)": "Training",
}
COMP = [("LIGA SAMPIONA", "Champions League"), ("LIGA ŠAMPIONA", "Champions League"), ("SUPERLIGA", "Super League"),
        ("SUPER LIGA", "Super League"), ("KUP", "Cup"), ("PRIJATELJSKA", "Friendly")]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_MEC = 45.0          # isti prag kao plan_nedelje.MIN_MINUTA_ZA_MEC


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        v = str(v).strip().replace(",", ".")
        return float(v) if v not in ("", "nan", "None") else None
    except ValueError:
        return None


def norm(s):
    return re.sub(r"[^a-z]", "", str(s or "").lower())


def fmt_m(v):
    return "{:,}".format(int(round(v or 0))).replace(",", ".")


def motor(data):
    """GPS 2.5 moduli (gym_dpp i drugi) iz foldera app-a; most ne upisuje nista u motor."""
    app = os.path.dirname(os.path.normpath(data))
    if app not in sys.path:
        sys.path.insert(0, app)
    import gym_dpp  # noqa: E402
    return gym_dpp


def plan_file_for(data, date):
    files = [f for f in glob.glob(os.path.join(data, "plan_kompletan_W*.csv")) if "prethodni" not in f and "_PRE_" not in f]
    files.sort(key=lambda f: (int(re.search(r"_W(\d+)", f).group(1)), os.path.getmtime(f)), reverse=True)
    for f in files:
        if any(r.get("datum") == date for r in read_csv(f)):
            return f
    return files[0] if files else None


def hhmm_in(text, kind):
    """Sat iz napomene mikrociklusa. kind='match' = poslednji sat u tekstu; 'train' = sat uz rec trening."""
    text = text or ""
    if kind == "match":
        m = re.findall(r"(\d{1,2}:\d{2})", text)
        return m[-1] if m else None
    m = re.search(r"[Tt]renin?g[^0-9:\n]{0,30}?(\d{1,2}:\d{2})", text)
    if m:
        return m.group(1)
    m = re.findall(r"(?<![Vv]ideo )(?<![Vv]ideo)(\d{1,2}:\d{2})", text)
    return m[0] if m else None


def minus_minutes(hhmm, minutes):
    h, m = [int(x) for x in hhmm.split(":")]
    t = (h * 60 + m - minutes) % (24 * 60)
    return "%02d:%02d" % (t // 60, t % 60)


def match_info(nap):
    """('Real Madrid', 'Home', 'Champions League') iz napomene MATCH reda."""
    nap = nap or ""
    comp = ""
    for k, v in COMP:
        if k in nap.upper():
            comp = v
            break
    opp, where = "", ""
    m = re.search(r"AEK\s*v\.?\s*([^()\d]+?)\s*\((dom|gost|home|away)\)", nap, re.I)
    if m:
        opp, where = m.group(1).strip(), ("Home" if m.group(2).lower() in ("dom", "home") else "Away")
    else:
        m = re.search(r"([A-ZČĆŠĐŽ][^()\d:]+?)\s*v\.?\s*AEK\s*\((dom|gost|home|away)\)", nap)
        if m:
            opp, where = m.group(1).strip(), ("Home" if m.group(2).lower() in ("dom", "home") else "Away")
        else:
            m = re.search(r"AEK\s*v\.?\s*([A-Za-zČĆŠĐŽčćšđž .]+)", nap)
            if m:
                opp = m.group(1).strip()
    return opp, where, comp


def micro_rows(data, plan_file):
    mp = os.path.join(data, os.path.basename(plan_file).replace("plan_kompletan_", "mikrociklus_"))
    return read_csv(mp)


def session_time(mrow, mikro=None):
    """(HH:MM, poznat) za red mikrociklusa; ako sat nije u tom redu, iz drugog reda istog dana i termina.
    Kad sat nije upisan nigde: AM 11:00 / PM 16:30, poznat=False."""
    nap = mrow.get("napomena", "") if mrow else ""
    tip = (mrow.get("tip_terena") or "").strip().upper() if mrow else ""
    t = hhmm_in(nap, "match" if tip == "MATCH" else "train")
    ses = (mrow.get("sesija") or "").strip().upper() if mrow else ""
    if not t and mrow and mikro and tip != "MATCH":
        for o in mikro:
            if o is mrow or o.get("datum") != mrow.get("datum") or (o.get("sesija") or "").strip().upper() != ses:
                continue
            if (o.get("tip_terena") or "").strip().upper() in ("MATCH", "OFF"):
                continue
            t = hhmm_in(o.get("napomena", ""), "train")
            if t:
                break
    if t:
        return ("%02d:%s" % (int(t.split(":")[0]), t.split(":")[1]), True)
    return ("16:30" if ses == "PM" else "11:00", False)


def micro_for(mikro, date, prow):
    """Red mikrociklusa koji odgovara redu plana (datum, grupa, sesija), pa bilo koji red tog datuma."""
    if not prow:
        return None
    g, s = (prow.get("grupa") or "").strip(), (prow.get("sesija") or "").strip()
    tip = (prow.get("tip_terena") or "").strip().upper()
    c = [m for m in mikro if m.get("datum") == date and (m.get("grupa") or "").strip() == g and (m.get("sesija") or "").strip() == s]
    if not c:
        c = [m for m in mikro if m.get("datum") == date and (m.get("grupa") or "").strip() == g]
    if not c:
        c = [m for m in mikro if m.get("datum") == date and (m.get("tip_terena") or "").strip().upper() == tip]
    if not c:
        c = [m for m in mikro if m.get("datum") == date and (m.get("sesija") or "").strip() == s and (m.get("tip_terena") or "").strip().upper() not in ("MATCH", "OFF")]
    return c[0] if c else None


def status_on(status_rows, name, date):
    for r in status_rows:
        if norm(r.get("igrac")) != norm(name):
            continue
        od, do = (r.get("datum_od") or "").strip(), (r.get("datum_do") or "").strip()
        if od and od <= date and (not do or do >= date) and (r.get("status") or "").upper() in ("POVREDA", "REHAB", "BOLEST"):
            return r
    return None


def status_en(r):
    nap = r.get("napomena", "") or ""
    m = re.search(r"EN:\s*(.+)$", nap)
    txt = m.group(1).strip() if m else ""
    txt = re.split(r"\s*·\s*", txt)[0] if txt else txt
    kind = {"POVREDA": "Injury or illness", "REHAB": "Rehab", "BOLEST": "Illness"}.get((r.get("status") or "").upper(), "Out")
    return kind, (txt or "Out of the team plan today. Follow the medical staff.")


def clean_title(t):
    """Naslov sesije bez tehnickih delova (2 MATCHES, MD+1/-2, PLAYED): 'UPPER + CORE' -> 'Upper + core'."""
    parts = [x.strip() for x in re.split(r"\s*·\s*", str(t or "")) if x.strip()]
    keep = [x for x in parts if not re.match(r"^(\d+\s*MATCHES?|MD[+\-/\d\s]*|PLAYED|DID NOT PLAY|NEW)$", x, re.I)]
    out = " · ".join(keep) or (parts[-1] if parts else "Gym")
    return out[:1].upper() + out[1:].lower()


def gym_payload(gdpp, D, ig):
    """Gym sesija igraca -> {title, slots:[{s, ex:[{n, d, note}]}]} isto kao Daily Player Plan."""
    ses = ig["sesija"]
    pl = D["pl"].get(ses["playerId"]) or {"name": ig["gym_name"]}
    redovi = gdpp._gym_redovi(ses, pl, ig["catapult"], D)
    slots = {}
    for slot, ime, nap, sr, ld, sub, k in redovi:
        s = str(slot)[:1].upper() or "A"
        d = sr.replace(" ", "") if sr else "%d×" % k
        note = " · ".join(x for x in (ld, sub, nap) if x)
        slots.setdefault(s, []).append({"n": ime, "d": d, "note": note})
    title = clean_title(re.sub(r"^\d{1,2}\.\d{1,2}\s*", "", str(ses.get("title") or "")))
    return {"title": title, "slots": [{"s": k, "ex": v} for k, v in sorted(slots.items())]}


def prep_blocks(D, ig):
    """Mobility + activation vezbe iz sesije -> checklista [{n, d, note}]."""
    ses = ig["sesija"]
    out = []
    for blok, lab in (("mobility", "mobility"), ("activation", "activation")):
        for b in ses.get("blocks", {}).get(blok) or []:
            eid = b if isinstance(b, str) else b.get("exerciseId")
            ex = D["ex"].get(eid, {})
            if ex.get("name"):
                out.append({"n": ex["name"], "d": "1 set", "note": lab})
    return out


def actual_time(daily, name, date):
    """Sat sesije iz imena Catapult exporta (2026_11_03_1623-...) za igraca i datum: sesija sa najvise minuta."""
    rows = [d for d in daily if d.get("Datum") == date and norm(d.get("Player")) == norm(name)]
    if not rows:
        return None
    r = max(rows, key=lambda d: num(d.get("Minutes")) or 0)
    m = re.search(r"\d{4}_\d{2}_\d{2}_(\d{2})(\d{2})-", str(r.get("Fajl") or ""))
    return "%s:%s" % (m.group(1), m.group(2)) if m else None


def results_for(daily, name, date):
    rows = [d for d in daily if d.get("Datum") == date and norm(d.get("Player")) == norm(name)]
    if not rows:
        return None
    return {"td": int(round(sum(num(d.get("TD_m")) or 0 for d in rows))),
            "hsr": int(round(sum(num(d.get("HSR_m")) or 0 for d in rows))),
            "spr": int(round(sum(num(d.get("Sprint_m")) or 0 for d in rows))),
            "vmax": max(num(d.get("MaxV_kmh")) or 0 for d in rows),
            "min": int(round(sum(num(d.get("Minutes")) or 0 for d in rows)))}


def choose_row(rows, is_match_day, played_min):
    """Red plana igraca za dan. Dan meca: pre uvoza svi MATCH; posle uvoza MATCH samo ko je igrao 45+."""
    if not rows:
        return None
    mec = [r for r in rows if (r.get("tip_terena") or "").strip().upper() == "MATCH"]
    ostali = [r for r in rows if r not in mec]
    if is_match_day and mec:
        if played_min is None:
            return mec[0]
        return mec[0] if (played_min >= MIN_MEC or not ostali) else ostali[0]
    if ostali:
        spec = [r for r in ostali if (r.get("grupa") or "") not in ("KLUB", "SVI", "STARTERI")]
        pool = spec or ostali
        return max(pool, key=lambda r: num(r.get("TD")) or 0)
    return mec[0]


def week_for(name, mikro, plan_rows_all, nastupi, daily, date, gym_titles):
    """Tab Week: jedan unos po danu mikrociklusa, samo iz plana i stvarnih minuta."""
    days = sorted({m.get("datum") for m in mikro if m.get("datum")})
    out = []
    for d in days:
        mrows = [m for m in mikro if m.get("datum") == d]
        is_match = any((m.get("tip_terena") or "").strip().upper() == "MATCH" for m in mrows)
        is_off = all((m.get("tip_terena") or "").strip().upper() in ("OFF", "DAY OFF", "") for m in mrows)
        mine = [r for r in plan_rows_all if r.get("datum") == d and norm(r.get("igrac")) == norm(name)]
        dd = dt.date.fromisoformat(d)
        ent = {"d": DOW[dd.weekday()], "n": "%02d" % dd.day, "date": d, "pill": (mrows[0].get("md") or "").strip() if mrows else "", "cls": "", "t": "", "s": ""}
        if is_match:
            mm = [m for m in mrows if (m.get("tip_terena") or "").strip().upper() == "MATCH"][0]
            opp, where, comp = match_info(mm.get("napomena"))
            t, _ = session_time(mm)
            ent.update(cls="match", pill="MATCH", t="Match %s" % t, s=" · ".join(x for x in (comp, opp, where) if x) or "Match")
            played = [n for n in nastupi if n.get("datum") == d and norm(n.get("igrac")) == norm(name)]
            res = results_for(daily, name, d)
            if played:
                ent["s"] = "%s · you played %d min" % (opp or "Match", int(round(num(played[0].get("min")) or 0)))
            elif res is not None and d <= date:
                ent["s"] = "%s · did not play · top-up %s m" % (opp or "Match", fmt_m(res["td"]))
        elif is_off:
            ent.update(cls="off", pill="OFF", t="Day off", s="Rest, food, walk. Check-in still counts.")
        else:
            row = choose_row(mine, False, None)
            mrow = micro_for(mikro, d, row) if row else (mrows[0] if mrows else None)
            t, known = session_time(mrow, mikro)
            at = actual_time(daily, name, d) if d <= date else None
            if at:
                t, known = at, True
            tip = (row.get("tip_terena") or "").strip().upper() if row else ""
            if row and (num(row.get("TD")) or 0) > 0:
                ent["t"] = "Training %s" % t if known else "Training (%s)" % ("morning" if t == "11:00" else "afternoon")
                ent["s"] = "%s · %s m · HSR %s" % (MODE_LABEL.get(tip, tip.title() or "Training"), fmt_m(num(row["TD"])), int(num(row.get("HSR")) or 0))
                res = results_for(daily, name, d)
                if res is not None and d < date:
                    ent["s"] = "%s · done %s m of %s" % (MODE_LABEL.get(tip, tip.title() or "Training"), fmt_m(res["td"]), fmt_m(num(row["TD"])))
            else:
                ent["t"] = "Gym only"
                ent["s"] = gym_titles.get(d) or (row.get("tip_gym") if row else "") or "No pitch session"
        out.append(ent)
    return out


def weeks_for(data, date, daily, ref90, engine, n=5):
    """Poslednjih n nedelja (plan_kompletan_W*): urađeno iz dnevnog niza, plan iz motora (isto kao Sidro),
    oba kao × sopstvene utakmice per 90. {ime: [{l, slug, done, plan, x, xp, closed}]}."""
    files = [f for f in glob.glob(os.path.join(data, "plan_kompletan_W*.csv")) if "prethodni" not in f and "_PRE_" not in f]
    weeks = []
    for f in files:
        rows = read_csv(f)
        ds = sorted({r.get("datum") for r in rows if r.get("datum")})
        if ds and ds[0] <= date:
            weeks.append((int(re.search(r"_W(\d+)", f).group(1)), ds[0], ds[-1]))
    weeks = sorted(weeks)[-n:]
    out = {}
    for wn, a, b in weeks:
        slug = "W%d" % wn
        try:
            plan_sums = engine.load_plan_kompletan_sums(slug, data_dir=data)
        except TypeError:
            plan_sums = engine.load_plan_kompletan_sums(slug)
        except Exception:  # noqa: BLE001
            plan_sums = {}
        da = dt.date.fromisoformat(a)
        lab = "%d %s" % (da.day, da.strftime("%b"))
        done = {}
        for r in daily:
            if a <= (r.get("Datum") or "") <= b:
                k = norm(r.get("Player"))
                d = done.setdefault(k, {"td": 0.0, "hsr": 0.0, "spr": 0.0})
                d["td"] += num(r.get("TD_m")) or 0; d["hsr"] += num(r.get("HSR_m")) or 0; d["spr"] += num(r.get("Sprint_m")) or 0
        for name, pr in plan_sums.items():
            k = norm(name)
            rf = ref90.get(k)
            if not rf:
                continue
            d = done.get(k, {"td": 0.0, "hsr": 0.0, "spr": 0.0})
            pl = {"td": num(pr.get("TD")) or 0, "hsr": num(pr.get("HSR")) or 0, "spr": num(pr.get("SPRINT")) or 0}
            x = {m: (round(d[m] / rf[m], 2) if rf[m] else None) for m in ("td", "hsr", "spr")}
            xp = {m: (round(pl[m] / rf[m], 2) if rf[m] else None) for m in ("td", "hsr", "spr")}
            out.setdefault(k, []).append({"l": lab, "slug": slug, "done": {m: int(round(v)) for m, v in d.items()},
                                          "plan": {m: int(round(v)) for m, v in pl.items()}, "x": x, "xp": xp, "closed": b < date})
    return out


def build(data, date, focus_default=None):
    gdpp = motor(data)
    D = gdpp.ucitaj(date, data)
    D["data_dir"] = data
    plan_file = plan_file_for(data, date)
    if not plan_file:
        raise SystemExit("Nema plan_kompletan_W*.csv u " + data)
    plan_all = read_csv(plan_file)
    mikro = micro_rows(data, plan_file)
    if not any(r.get("datum") == date for r in plan_all):
        raise SystemExit("U %s nema redova za %s" % (os.path.basename(plan_file), date))
    base = {r["Player"]: r for r in read_csv(os.path.join(data, "W1_baza_kamp.csv"))}
    # referenca = SOPSTVENA UTAKMICA per 90 (mec_referenca.csv, isto kao Sidro u GPS 2.5); kamp nedelja vise nije referenca
    ref90 = {}
    for r in read_csv(os.path.join(data, "mec_referenca.csv")):
        ref90[norm(r.get("igrac"))] = {"td": num(r.get("TD_90")) or 0, "hsr": num(r.get("HSR_90")) or 0, "spr": num(r.get("SPR_90")) or 0,
                                       "src": ("own match (%s)" % (r.get("n_meceva") or "").strip()) if (r.get("izvor") or "") == "igrac" else "position average",
                                       "n": r.get("n_meceva") or "", "matches": r.get("mecevi") or ""}
    import aek_gps_report as engine  # noqa: E402  (motor() je vec dodao folder app-a u sys.path)
    weeks_all = weeks_for(data, date, D["niz"], ref90, engine)
    vmax_baza = {r["Player"]: num(r.get("MaxV_licni")) for r in read_csv(os.path.join(data, "max_velocity_baza.csv"))}
    daily = D["niz"]
    nastupi = D["nastupi"]
    status_rows = read_csv(os.path.join(data, "status_igraca.csv"))
    focus_rows = read_csv(os.path.join(data, "hub_focus.csv"))
    is_match_day = any(m.get("datum") == date and (m.get("tip_terena") or "").strip().upper() == "MATCH" for m in mikro)
    match_imported = is_match_day and any(d.get("Datum") == date for d in daily)
    match_row_m = next((m for m in mikro if m.get("datum") == date and (m.get("tip_terena") or "").strip().upper() == "MATCH"), None)

    # gym sesije dana (sa zamenama po kodovima), isto kao DPP
    igraci = gdpp.igraci_za_datum(date, D)
    try:
        gdpp._prilagodi_za_pdf(igraci, date, D)
    except Exception as e:  # noqa: BLE001 - zamene nisu obavezne za hub
        print("UPOZORENJE: zamene po kodovima nisu primenjene:", e)
    gym_by = {norm(ig["catapult"]): ig for ig in igraci}
    gym_titles_by_player = {}
    for s in D["state"]["sessions"]:
        p = D["pl"].get(s.get("playerId"))
        if not p:
            continue
        cat = D["mapa"].get(p["name"].strip().upper()) or p["name"].title()
        gym_titles_by_player.setdefault(norm(cat), {})[s.get("date")] = clean_title(re.sub(r"^\d{1,2}\.\d{1,2}\s*", "", str(s.get("title") or "")))

    # sledeci mec (od danas, ukljucujuci danas)
    nxt = None
    for m in sorted([m for m in mikro if (m.get("tip_terena") or "").strip().upper() == "MATCH" and m.get("datum", "") >= date], key=lambda m: m["datum"]):
        opp, where, comp = match_info(m.get("napomena"))
        t, _ = session_time(m)
        dd = dt.date.fromisoformat(m["datum"])
        nxt = {"date": m["datum"], "time": t, "opp": opp or comp or "Match", "comp": comp, "where": where,
               "label": "%s · %s %02d.%02d %s" % (where or "Match", DOW[dd.weekday()], dd.day, dd.month, t)}
        break
    wk_label = ""
    days = sorted({m.get("datum") for m in mikro if m.get("datum")})
    if days:
        a, b = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
        n_mec = len({m["datum"] for m in mikro if (m.get("tip_terena") or "").strip().upper() == "MATCH"})
        wn = re.search(r"_W(\d+)", plan_file).group(1)
        wk_label = "Week %s · %02d to %02d %s · %d match%s" % (wn, a.day, b.day, b.strftime("%B"), n_mec, "" if n_mec == 1 else "es")
    published = dt.datetime.now().strftime("%d.%m %H:%M")

    names = sorted({(r.get("igrac") or "").strip() for r in plan_all} | {ig["catapult"] for ig in igraci})
    plan, results, skipped = [], [], []
    for name in names:
        pid = NAME_TO_ID.get(name)
        if not pid:
            skipped.append(name)
            continue
        res = results_for(daily, name, date)
        rows = [r for r in plan_all if r.get("datum") == date and norm(r.get("igrac")) == norm(name)]
        played = None
        if is_match_day and match_imported:
            n = [x for x in nastupi if x.get("datum") == date and norm(x.get("igrac")) == norm(name)]
            played = num(n[0].get("min")) if n else 0.0
        row = choose_row(rows, is_match_day, played)
        mrow = micro_for(mikro, date, row) if row else None
        st = status_on(status_rows, name, date)
        ig = gym_by.get(norm(name))
        gym = gym_payload(gdpp, D, ig) if ig else None
        prep = prep_blocks(D, ig) if ig else []

        ref = base.get(name, {})
        r90 = ref90.get(norm(name)) or {}
        ref_td, ref_hsr, ref_spr = (r90.get("td") or None), (r90.get("hsr") or None), (r90.get("spr") or None)
        brz = gdpp._brzina(name, date, D)
        ref_v = max([v for v in (vmax_baza.get(name), (brz or {}).get("best"), num(ref.get("MaxV_kmh"))) if v] or [0]) or None
        speed_days = ""
        last_speed = ""
        if brz:
            pts = [v for d_, v in brz["pts"]]
            last_speed = pts[-1] if pts else ""
            if ref_v:
                prag = 0.95 * ref_v
                hits = [r["Datum"] for r in D["brzina"] if norm(r.get("Player")) == norm(name) and r.get("Datum", "") < date and (num(r.get("MaxV_kmh")) or 0) >= prag]
                speed_days = (dt.date.fromisoformat(date) - dt.date.fromisoformat(max(hits))).days if hits else ""
        last_match = [x for x in nastupi if norm(x.get("igrac")) == norm(name) and x.get("datum", "") < date]
        last_min = int(round(num(max(last_match, key=lambda x: x["datum"]).get("min")) or 0)) if last_match else 0

        focus = focus_default or ""
        for fr in focus_rows:
            if fr.get("date") == date and fr.get("player") in ("*", pid, name):
                focus = fr.get("text", focus)

        tip = (row.get("tip_terena") or "").strip().upper() if row else ""
        t_sess, t_known = session_time(mrow, mikro) if mrow else ("11:00", False)
        at = actual_time(daily, name, date)
        if at and not is_match_day:
            t_sess, t_known = at, True
        md = ((row.get("md") if row else "") or (mrow.get("md") if mrow else "") or "").strip()
        if not md:
            md = next(((m.get("md") or "").strip() for m in mikro if m.get("datum") == date and (m.get("md") or "").strip()), "")
        ciljevi = gdpp._ciljevi(name, date, D) if (row and (num(row.get("TD")) or 0) > 0 and tip != "MATCH") else None
        td, hsr, spr = (num(row.get("TD")), num(row.get("HSR")), num(row.get("SPRINT"))) if row else (None, None, None)
        cilj_v = num(row.get("cilj_max_v_kmh")) if row else None
        cap_pct = speed_goal = ""
        if cilj_v and ref_v and td:
            pct = round(cilj_v / ref_v * 100)
            plafon = ciljevi["plafon"] if ciljevi else (pct < 95)
            if tip == "MATCH":
                speed_goal = 95
            elif plafon:
                cap_pct = min(pct, 94)
            else:
                speed_goal = max(pct, 95)
        off = tip in ("OFF", "DAY OFF")
        gym_only = not off and not (td and td > 0)

        if st:
            kind, txt = status_en(st)
            mode, sub = kind, txt
            day_type = "%s · %s" % (md or "Today", "Out of the team plan")
            td = hsr = spr = None
            cap_pct = speed_goal = ""
            gym_only = bool(gym)
        elif off:
            mode, day_type = "Day off", "%s · Day off" % md
            sub = "Day off. Sleep, eat well, walk. Your check-in still counts."
        elif tip == "MATCH":
            opp, where, comp = match_info((match_row_m or {}).get("napomena"))
            mode = "Match day"
            day_type = "%s · Match %s" % (md or "MD", t_sess)
            sub = "%s%s. Kick-off %s. Targets = 100 %% of your own match reference, scaled to your minutes." % (
                (comp + " · ") if comp else "", (opp + (" (%s)" % where.lower() if where else "")) if opp else "Match", t_sess)
            if match_imported and res:
                sub = "%s%s. You played %d minutes." % ((comp + " · ") if comp else "", opp or "Match", int(round(played or 0)))
        else:
            tip_key = ciljevi["tip"] if ciljevi else ((mrow.get("tip_dana") if mrow else "") or md)
            grupa = (row.get("grupa") if row else "") or ""
            why = gdpp._why(tip_key, grupa, D) if tip_key else ""
            if not why and tip_key:
                why = gdpp._why(tip_key.split("_")[0], grupa, D)
            if gym_only:
                mode = "Gym only"
                gt = (gym or {}).get("title") or clean_title((row.get("tip_gym") if row else "") or (mrow.get("tip_gym") if mrow else "")) or "gym"
                if last_min >= MIN_MEC:
                    sub = "You played %d minutes in the last match. No pitch today, gym only: %s." % (last_min, gt)
                else:
                    sub = "No pitch session today, gym only: %s." % gt
                day_type = "%s · Gym %s" % (md, t_sess if t_known else ("(morning)" if t_sess == "11:00" else "(afternoon)"))
            else:
                mode = MODE_LABEL.get(tip, tip.title() or "Training")
                sub = why or "%s. Targets are a share of your own match reference." % mode
                day_type = "%s · Training %s" % (md, t_sess if t_known else "(time tbc)")
                if tip == "POST-MATCH TOP-UP":
                    day_type = "%s · Top-up after the match" % md
                    opp, where, comp = match_info((match_row_m or {}).get("napomena"))
                    if played is not None:
                        sub = "%s: you played %d minutes. Top-up after the match: 40/65/30 %% of your match reference plus flying sprints at 95 %% or more." % (opp or "Match", int(round(played)))

        act_time = "" if (off or st) else minus_minutes(t_sess, 30)
        act_group = "" if (off or st) else ("Group activation with the team" if not gym_only else "Activation before the gym")
        act_indiv = "; ".join(x["n"] for x in prep) if prep else ""
        mobility = prep if (gym_only and prep) else ""
        extra = {
            "session_time": t_sess, "time_known": t_known, "gym_only": gym_only, "match_day": is_match_day,
            "match_imported": match_imported, "played_min": (int(round(played)) if played is not None else None),
            "next": nxt, "week_label": wk_label, "published": published,
            "week": week_for(name, mikro, plan_all, nastupi, daily, date, gym_titles_by_player.get(norm(name), {})),
            "ref_src": r90.get("src") or "", "ref_matches": r90.get("matches") or "",
            "weeks": weeks_all.get(norm(name), []),
        }
        plan.append({
            "date": date, "player": pid,
            "day_type": day_type, "mode_label": mode, "sub": sub, "focus": focus,
            "pitch_td": int(td) if td else "", "pitch_hsr": int(hsr) if hsr else "", "pitch_spr": int(spr) if spr else "",
            "cap_pct": cap_pct, "speed_goal": speed_goal,
            "speed_work": ("Top speed exposure in the session" if (speed_goal and tip != "MATCH") else ""),
            "act_time": act_time, "act_group": act_group, "act_indiv": act_indiv,
            "mobility_json": mobility, "gym_json": gym or "",
            "ref_td": int(ref_td) if ref_td else "", "ref_hsr": int(ref_hsr) if ref_hsr else "", "ref_spr": int(ref_spr) if ref_spr else "",
            "ref_vmax": ref_v or "", "speed_days": speed_days, "last_speed": last_speed, "last_min": last_min,
            "extra_json": extra,
        })
        if res:
            results.append({"date": date, "player": pid, "td": res["td"], "hsr": res["hsr"], "spr": res["spr"], "vmax": res["vmax"]})
    return plan, results, skipped, plan_file


def send(url, key, plan, results):
    body = json.dumps({"action": "feed", "key": key, "plan": plan, "results": results}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Most GPS 2.5 -> AEK Player Hub")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD (podrazumevano danas)")
    ap.add_argument("--data", default=DEFAULT_DATA, help="GPS 2.5 data folder")
    ap.add_argument("--url", default=os.environ.get("AEK_HUB_URL", ""), help="Apps Script web app URL")
    ap.add_argument("--key", default=os.environ.get("AEK_HUB_KEY", ""), help="staff PIN iz lista Players")
    ap.add_argument("--focus", default=None, help="fokus dana za sve igrace (ako nema hub_focus.csv)")
    ap.add_argument("--dry-run", action="store_true", help="samo ispisi, ne salji")
    a = ap.parse_args()
    plan, results, skipped, plan_file = build(a.data, a.date, a.focus)
    print("Plan: %s | datum %s | %d igraca, %d rezultata" % (os.path.basename(plan_file), a.date, len(plan), len(results)))
    if skipped:
        print("Preskoceno (nema u NAME_TO_ID):", ", ".join(sorted(set(skipped))))
    for p in plan:
        g = p["gym_json"]
        print("  %-16s %-30s %-18s TD %-5s HSR %-4s SPR %-4s cap %-3s goal %-3s gym: %s" % (
            p["player"], p["day_type"][:30], p["mode_label"][:18], p["pitch_td"], p["pitch_hsr"], p["pitch_spr"], p["cap_pct"], p["speed_goal"],
            (g.get("title") + " (%d)" % sum(len(s["ex"]) for s in g["slots"])) if g else "-"))
    if a.dry_run or not a.url:
        out = os.path.join(a.data, "hub_feed_%s.json" % a.date)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"plan": plan, "results": results}, f, ensure_ascii=False, indent=1)
        print("Nije poslato (dry-run ili nema --url). Paket upisan u", out)
        return
    resp = send(a.url, a.key, plan, results)
    print("Odgovor:", resp)
    if not resp.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
