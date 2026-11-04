"""
player_hub_feed.py: most iz AEK GPS 2.5 podataka u AEK Player Hub (Google tabela preko Apps Script-a).

Za zadati datum sastavi po igraču:
  - plan dana iz data/plan_kompletan_W<N>.csv (tip terena, ciljevi TD/HSR/SPRINT, cilj max brzine, tip gym-a)
  - referentne brojke iz data/W1_baza_kamp.csv i data/max_velocity_baza.csv
  - dane od poslednje izloženosti brzini iz data/brzina_dnevnik.csv
  - minute od juče iz data/minuti_<juce>.csv ili dnevnog niza
  - gym program iz data/gym/gym_export_latest.json (sesija za taj datum i igrača)
  - rezultat sesije iz data/dnevni_niz.csv (ako je trening već uvezen)
  - fokus dana iz data/hub_focus.csv (date,player,text; player "*" važi za sve) ili iz dpp_why.csv

Pokretanje (iz AEK_GPS_APP_DEMO foldera ili bilo gde uz --data):
  python player_hub_feed.py --date 2026-11-05 --url "https://script.google.com/macros/s/.../exec" --key 2468
  python player_hub_feed.py --date 2026-11-05 --dry-run        (samo ispiše šta bi poslao, ništa ne šalje)

Posle treninga, kad uvezeš Catapult izvoz u GPS 2.5, pokreni isto: tada šalje i Results.
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
    "SPEED": "Speed day", "TACTICAL": "Tactical session", "MATCH": "Match day", "OFF": "Day off",
}


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


def latest_plan_file(data):
    files = [f for f in glob.glob(os.path.join(data, "plan_kompletan_W*.csv")) if "prethodni" not in f and "_PRE_" not in f]
    if not files:
        files = [f for f in glob.glob(os.path.join(data, "plan_kompletan_W*.csv")) if "prethodni" not in f]
    if not files:
        return None
    files.sort(key=lambda f: (int(re.search(r"_W(\d+)", f).group(1)), os.path.getmtime(f)))
    return files[-1]


def plan_file_for(data, date):
    """Plan nedelje koji sadrži dati datum (najnovija nedelja ima prednost). Za stare datume uzima W16, W17..."""
    files = [f for f in glob.glob(os.path.join(data, "plan_kompletan_W*.csv")) if "prethodni" not in f and "_PRE_" not in f]
    files.sort(key=lambda f: (int(re.search(r"_W(\d+)", f).group(1)), os.path.getmtime(f)), reverse=True)
    for f in files:
        if any(r.get("datum") == date for r in read_csv(f)):
            return f
    return latest_plan_file(data)


def training_time(text):
    m = re.search(r"Trening\s+(\d{1,2}:\d{2})", text or "")
    return m.group(1) if m else "11:00"


def minus_minutes(hhmm, minutes):
    h, m = [int(x) for x in hhmm.split(":")]
    t = (h * 60 + m - minutes) % (24 * 60)
    return "%02d:%02d" % (t // 60, t % 60)


def gym_for(sessions, gym_name, date):
    """Gym sesija iz gym izvoza -> {title, slots:[{s,ex:[{n,d,note}]}]} u obliku koji app očekuje."""
    cands = [s for s in sessions if s.get("date") == date and str(s.get("player", "")).strip().upper() == gym_name]
    if not cands:
        return None
    s = cands[-1]
    slots = {}
    for it in s.get("items", []):
        slot = str(it.get("slot", "A1"))[:1] or "A"
        kg = it.get("kg")
        pct = it.get("pct")
        if it.get("load_type") == "bw":
            note = "bodyweight"
        elif pct:
            note = "%d%% 1RM" % round(pct * 100) + (" · %s kg" % kg if kg else "")
        elif kg:
            note = "%s kg" % kg
        else:
            note = it.get("category", "")
        slots.setdefault(slot, []).append({"n": it.get("exercise", ""), "d": "%s×%s" % (it.get("sets", 0), it.get("reps", "")), "note": note})
    return {"title": re.sub(r"^\d{1,2}\.\d{1,2}\s*", "", str(s.get("title", ""))).strip() or "Gym", "slots": [{"s": k, "ex": v} for k, v in sorted(slots.items())]}


def build(data, date, focus_default=None):
    plan_file = plan_file_for(data, date)
    if not plan_file:
        raise SystemExit("Nema plan_kompletan_W*.csv u " + data)
    plan_rows = [r for r in read_csv(plan_file) if r.get("datum") == date]
    if not plan_rows:
        raise SystemExit("U %s nema redova za %s" % (os.path.basename(plan_file), date))
    base = {r["Player"]: r for r in read_csv(os.path.join(data, "W1_baza_kamp.csv"))}
    vmax = {r["Player"]: num(r.get("MaxV_licni")) for r in read_csv(os.path.join(data, "max_velocity_baza.csv"))}
    speed_log = read_csv(os.path.join(data, "brzina_dnevnik.csv"))
    daily = read_csv(os.path.join(data, "dnevni_niz.csv"))
    yday = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    minutes = {r["Player"]: num(r.get("Minutes")) for r in read_csv(os.path.join(data, "minuti_%s.csv" % yday))}
    if not minutes:
        for r in daily:
            if r.get("Datum") == yday:
                minutes[r["Player"]] = (minutes.get(r["Player"]) or 0) + (num(r.get("Minutes")) or 0)
    mapping = {r["gym_name"].strip().upper(): r["catapult_name"].strip() for r in read_csv(os.path.join(data, "gym", "player_mapping.csv")) if r.get("catapult_name")}
    gym_name_of = {v: k for k, v in mapping.items()}
    sessions = []
    gexp = os.path.join(data, "gym", "gym_export_latest.json")
    if os.path.exists(gexp):
        with open(gexp, encoding="utf-8") as f:
            j = json.load(f)
        sessions = j.get("sessions", j) if isinstance(j, dict) else j
    focus_rows = read_csv(os.path.join(data, "hub_focus.csv"))
    why = {(r.get("tip_dana", ""), r.get("grupa", "")): r.get("tekst", "") for r in read_csv(os.path.join(data, "dpp_why.csv"))}
    # tip dana po (datum, grupa) iz mikrociklusa iste nedelje; dpp_why je ključan po tip_dana
    micro_files = [f for f in glob.glob(os.path.join(data, "mikrociklus_W*.csv")) if "_PRE_" not in f]
    micro_files.sort(key=lambda f: (int(re.search(r"_W(\d+)", f).group(1)), os.path.getmtime(f)))
    tip_dana = {}
    for f in micro_files[-2:]:
        for r in read_csv(f):
            tip_dana[(r.get("datum", ""), r.get("grupa", ""))] = r.get("tip_dana", "")

    plan, results, skipped = [], [], []
    minuti_dan = {}
    for d in read_csv(os.path.join(data, "dnevni_niz.csv")):
        if d.get("Datum") == date:
            minuti_dan[d["Player"]] = minuti_dan.get(d["Player"], 0) + (num(d.get("Minutes")) or 0)
    po_igracu = {}
    for r in plan_rows:
        po_igracu.setdefault(r.get("igrac", "").strip(), []).append(r)
    izabrani = []
    for ime, redovi in po_igracu.items():
        if len(redovi) == 1:
            izabrani.append(redovi[0])
            continue
        mec = [x for x in redovi if (x.get("tip_terena") or "").strip().upper() == "MATCH"]
        ostali = [x for x in redovi if x not in mec]
        igrao = minuti_dan.get(ime, 0) >= 45
        izabrani.append((mec[0] if (igrao and mec) or not ostali else ostali[0]))
    plan_rows = izabrani

    for r in plan_rows:
        name = r.get("igrac", "").strip()
        pid = NAME_TO_ID.get(name)
        if not pid:
            skipped.append(name)
            continue
        ref = base.get(name, {})
        ref_td, ref_hsr, ref_spr = num(ref.get("TD_m")), num(ref.get("HSR_m")), num(ref.get("Sprint_m"))
        ref_v = vmax.get(name) or num(ref.get("MaxV_kmh"))
        td, hsr, spr = num(r.get("TD")), num(r.get("HSR")), num(r.get("SPRINT"))
        cilj_v = num(r.get("cilj_max_v_kmh"))
        cap_pct = speed_goal = ""
        if cilj_v and ref_v:
            pct = round(cilj_v / ref_v * 100)
            if pct < 93:
                cap_pct = pct
            else:
                speed_goal = pct
        tip = (r.get("tip_terena") or "").strip().upper()
        napomena = r.get("napomena", "")
        t_train = training_time(napomena)
        last_hit = None
        for sr in speed_log:
            if sr.get("Player") == name and ref_v and (num(sr.get("MaxV_kmh")) or 0) >= 0.95 * ref_v and sr.get("Datum", "") < date:
                last_hit = max(last_hit or "", sr["Datum"])
        speed_days = (dt.date.fromisoformat(date) - dt.date.fromisoformat(last_hit)).days if last_hit else ""
        last_speed = ""
        mine = [sr for sr in speed_log if sr.get("Player") == name and sr.get("Datum", "") < date]
        if mine:
            last_speed = num(mine[-1].get("MaxV_kmh")) or ""
        focus = focus_default or ""
        for fr in focus_rows:
            if fr.get("date") == date and fr.get("player") in ("*", pid, name):
                focus = fr.get("text", focus)
        td_key = tip_dana.get((date, r.get("grupa", "")), "")
        # dpp_why ima opšte ključeve (MD-1, MD-2, MD+1_KOMPENZACIJA); mikrociklus ima finije (MD-1_IZMEDJU_2M, MD+1/-2_KOMP_LAKA)
        cands = [td_key, td_key.split("_")[0]]
        if "KOMP" in td_key:
            cands.append("MD+1_KOMPENZACIJA")
        sub = ""
        for ck in cands:
            sub = why.get((ck, r.get("grupa", ""))) or why.get((ck, "")) or ""
            if sub:
                break
        if not sub:
            sub = "Day off. Sleep, eat well, walk. Your check-in still counts." if (tip in ("OFF", "DAY OFF")) else "%s. Targets are a share of your own match reference." % MODE_LABEL.get(tip, tip.title() or "Training")
        gym = gym_for(sessions, gym_name_of.get(name, name.upper()), date)
        if not gym and r.get("tip_gym"):
            gym = {"title": r["tip_gym"].strip(), "slots": []}
        off = tip in ("OFF", "DAY OFF") or (not td and not hsr and not spr and not r.get("tip_gym"))
        plan.append({
            "date": date, "player": pid,
            "day_type": "%s · %s" % (r.get("md", "").strip(), "Day off" if off else ("Match " + t_train if tip == "MATCH" else "Training " + t_train)),
            "mode_label": MODE_LABEL.get(tip, tip.title() or "Training"),
            "sub": sub, "focus": focus,
            "pitch_td": int(td) if td else "", "pitch_hsr": int(hsr) if hsr else "", "pitch_spr": int(spr) if spr else "",
            "cap_pct": cap_pct, "speed_goal": speed_goal,
            "speed_work": "Top speed exposure in the session" if speed_goal else "",
            "act_time": "" if off else minus_minutes(t_train, 30), "act_group": "" if off else "Group activation with the team", "act_indiv": "",
            "mobility_json": "", "gym_json": gym or "",
            "ref_td": int(ref_td) if ref_td else "", "ref_hsr": int(ref_hsr) if ref_hsr else "", "ref_spr": int(ref_spr) if ref_spr else "",
            "ref_vmax": ref_v or "", "speed_days": speed_days, "last_speed": last_speed,
            "last_min": int(round(minutes.get(name) or 0)),
        })
        done = [d for d in daily if d.get("Datum") == date and d.get("Player") == name]
        if done:
            results.append({"date": date, "player": pid,
                            "td": int(round(sum(num(d.get("TD_m")) or 0 for d in done))),
                            "hsr": int(round(sum(num(d.get("HSR_m")) or 0 for d in done))),
                            "spr": int(round(sum(num(d.get("Sprint_m")) or 0 for d in done))),
                            "vmax": max(num(d.get("MaxV_kmh")) or 0 for d in done)})
    return plan, results, skipped, plan_file


def send(url, key, plan, results):
    body = json.dumps({"action": "feed", "key": key, "plan": plan, "results": results}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Most GPS 2.5 -> AEK Player Hub")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD (podrazumevano danas)")
    ap.add_argument("--data", default=DEFAULT_DATA, help="GPS 2.5 data folder")
    ap.add_argument("--url", default=os.environ.get("AEK_HUB_URL", ""), help="Apps Script web app URL")
    ap.add_argument("--key", default=os.environ.get("AEK_HUB_KEY", ""), help="staff PIN iz lista Players")
    ap.add_argument("--focus", default=None, help="fokus dana za sve igrače (ako nema hub_focus.csv)")
    ap.add_argument("--dry-run", action="store_true", help="samo ispiši, ne šalji")
    a = ap.parse_args()
    plan, results, skipped, plan_file = build(a.data, a.date, a.focus)
    print("Plan: %s | datum %s | %d igrača, %d rezultata" % (os.path.basename(plan_file), a.date, len(plan), len(results)))
    if skipped:
        print("Preskočeno (nema u NAME_TO_ID):", ", ".join(sorted(set(skipped))))
    for p in plan[:3]:
        print("  ", p["player"], p["day_type"], p["mode_label"], "TD", p["pitch_td"], "HSR", p["pitch_hsr"], "SPR", p["pitch_spr"],
              "cap", p["cap_pct"], "goal", p["speed_goal"], "gym:", (p["gym_json"] or {}).get("title") if p["gym_json"] else "-")
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
