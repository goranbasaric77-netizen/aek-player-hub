# AEK Player Hub: predaja stanja (04.11.2026)

Ovaj fajl je dovoljan da bilo koji agent (Cowork, Claude Code) nastavi rad. Pročitaj ga ceo pre prve izmene.

## Šta je ovo

App za igrače AEK Athens FC: svaki dan vide tip dana, ciljeve na terenu, gym program i fokus staffa, rade jutarnji
check-in i „zatvaraju tri prstena" (check-in, sesija, gym). Staff ima tab Team sa tabelom svih igrača.
Jezik app-a je engleski (internacionalna svlačionica). Vlasnik: Goran Bašarić, Head of Performance.

## Gde šta stoji

```
AEK_PLAYER_HUB/
  index.html            ceo app (HTML + CSS + JS u jednom fajlu, bez build-a)
  config.js             window.AEK_SYNC = { url: "" }  -> prazan = skica, URL = živo
  photos/<id>.webp      portreti igrača (27), id kao u ROSTER nizu
  crest.webp            grb kluba
  manifest.webmanifest, sw.js, icon-192.png, icon-512.png, apple-touch-icon.png   PWA
  backend/Code.gs       Google Apps Script (tabela sa listovima Players, Plan, Results, Log, Tokens, Today)
  backend/UPUTSTVO.md   korak po korak kako se tabela i skript postave (radi Goran, 15 min)
  bridge/player_hub_feed.py   most iz GPS 2.5 podataka u hub (plan + rezultati po datumu)
  README.md, PREDAJA.md
```

GPS 2.5 podaci: `C:\Users\goran\OneDrive\Radna površina\AEK_GPS_APP\AEK_GPS_APP_DEMO\data\`
(plan_kompletan_W<N>.csv, mikrociklus_W<N>.csv, dnevni_niz.csv, brzina_dnevnik.csv, max_velocity_baza.csv,
W1_baza_kamp.csv, minuti_<datum>.csv, gym/gym_export_latest.json, gym/player_mapping.csv, dpp_why.csv).

Lokalni pregled: na Desktopu postoji `.claude/launch.json` sa konfiguracijom „player-hub" (python http.server 8765),
pa je app na http://localhost:8765/AEK_PLAYER_HUB/index.html. Dupli klik na index.html takođe radi.

Objava: GitHub repo goranbasaric77-netizen/aek-player-hub, GitHub Pages sa main grane.
Nova verzija = `git add -A && git commit -m "..." && git push`, pa podići `CACHE` u sw.js.

## Kako app radi iznutra (index.html)

- Podaci igrača: `ROSTER` (id, ime, pozicija, foto) -> `buildPlayer` pravi demo profil iz četiri detaljna (`DETAILED`).
  U živom režimu `applyPlan(p, planRow)` zamenjuje demo sadržaj redom iz tabele.
- Stanje po igraču i danu: localStorage ključ `aekhub2:p:<id>` = {checkins, gym, mob, ack} po datumu `TK`.
- Prstenovi: `ringsOf(player, stateOverride)` vraća vals [check-in, session, gym], score, closed.
  Session = GPS ciljevi (svaki cilj ispunjen od 90 %) ili mobility checklista; bez ijednog = 100 („No session planned").
- Živi režim (`LIVE` = postoji CFG.url): `tryEnter` proverava PIN preko `auth`; `syncToday` vuče `today` (plan, result,
  stanje sa servera, team pulse); svaka akcija ide kroz `enqueue` -> red `aekhub2:queue` -> `flush` -> `log`.
  Bez interneta red čeka, šalje se na `online` ili kad se app vrati u prvi plan. Tačkica u zaglavlju: zeleno poslato,
  žuto čeka, crveno nema veze.
- Staff: `enterStaff` -> tab Team -> `loadTeam` (`team` akcija) -> `liveRows`; klik na igrača `openPlayer` -> `adoptLive`
  upisuje stanje sa servera lokalno pa otvara njegove ekrane. U skici isto rade `demoRow`/`seedDemo`.
- Vreme: `weatherCard` (Open-Meteo, Spata 37.962/23.913, sati 10-13), keš 30 min `aekhub2:wx`, bez mreže WX_DEMO.
- Check-in: pet pitanja sa licima (`face`, `FACE_COL`), sati sna, mapa tela, beleška; readiness = `readinessOf`
  (ista formula je u Code.gs `readiness`).
- Sketch dugme dole (samo u skici): jutro / posle sesije (`demoAfter`).

## API ugovor (Code.gs i mock su isti)

POST na web app URL, telo JSON kao text/plain, odgovor JSON:
- `{action:"auth", player, pin, device}` -> `{ok, token, player, name, role}` ili `{ok:false, error:"pin"|"player"}`
- `{action:"today", token, date}` -> `{ok, plan|null, result|null, state, team:{total, checkedIn}}`
- `{action:"log", token, events:[{ts, date, type, key, value}]}` types: open, checkin, gym, mob, ack
- `{action:"team", token(staff), date}` -> `{ok, rows:[{player, name, state, plan, result}]}`
- `{action:"feed", key(staff PIN), plan:[...], results:[...]}` -> upsert po (date, player)
- `{action:"history", token, date, days, player?}` -> `{ok, player, days:[{date, plan, result, state}]}` (N dana pre `date`; staff šalje `player`, igrač dobija svoje)
Plan red = kolone lista Plan (vidi SHEETS u Code.gs); `gym_json` i `mobility_json` su JSON u istom obliku kao P.gym / P.mobility.

## Šta je gotovo i provereno (04.11.2026)

- Skica: ceo app sa 29 igrača, staff tabela, lica, vreme uživo, provereno u browseru (telefon i desktop, dark i light).
- Živi režim testiran na lokalnom mock serveru sa istim API-jem: pogrešan PIN odbijen, prijava, plan sa servera,
  check-in i serije stižu u log, rezultat zatvara zeleni prsten, offline red se šalje kad se veza vrati,
  staff tabela uživo, otvaranje igrača, igrač bez plana („Plan not published yet").
- Most testiran na pravim GPS podacima (02.11: 16 igrača + 14 rezultata; 03.11: 26 igrača).

## Živi zadnji deo (napravljeno 04.11.2026)

- Google tabela „AEK Player Hub" na goranbasaric77@gmail.com: https://docs.google.com/spreadsheets/d/16DFYiEveVmyC72g3lR94-m7R0yM2u7fYh40rrjKldsw/edit
- Apps Script: samostalan projekat (nije vezan za tabelu), Code.gs ima `SHEET_ID` i otvara tabelu po ID-u.
  Editor: https://script.google.com/home (projekat „Untitled project", slobodno preimenovati).
- Web app URL stoji u `config.js`. Posle izmene Code.gs: Deploy > Manage deployments > olovka > New version > Deploy (URL ostaje isti).
- List Players (04.11.2026): staff red + svih 29 igrača iz ROSTER-a. PIN-ove igrača je generisao skript na serveru;
  Goran ih čita iz tabele, agent ih ne zapisuje nigde (ni u repo). Izmene u tabeli raditi privremenom funkcijom
  u Code.gs (setValue), ne kucanjem u ćelije kroz browser panel (upis se gubi).
- Slanje plana: dugme „POŠALJI PLAN U PLAYER HUB" u AEK PERFORMANCE HUB launcheru (AEK_GPS_APP\aek_hub.pyw), sa
  poljem FOKUS DANA. Staff PIN se pita jednom i čuva lokalno u %APPDATA%\AEK_HUB\player_hub.json.

## Jutarnji podsetnik (OneSignal web push, 04.11.2026)

- OneSignal app „AEK Player Hub" (Goranov nalog), integracija Custom code. App ID je u `config.js` (`onesignal`),
  REST ključ je samo u Script Properties (`ONESIGNAL_KEY`), nikad u kodu.
- App: kartica „Morning reminder at 08:30" na Today (stanja ask/on/denied/ios), `OneSignal.login(player id)` povezuje
  telefon sa igračem (external_id). `sw.js` uvozi OneSignal worker; `OneSignalSDKWorker.js` samo prosleđuje na `sw.js`.
  serviceWorkerPath mora biti relativan na koren sajta (`aek-player-hub/sw.js`), ne samo `sw.js`.
- Skript: `sendMorningReminder` šalje igračima koji imaju plan za danas i još nisu uradili check-in; okidač pravi
  `setupReminders` (svaki dan oko 08:30 Europe/Athens, napravljen 04.11).
- iPhone: obaveštenja rade samo kad je app dodat na početni ekran i otvoren odatle.

## Istorija i Progress (04.11.2026)

- Code.gs 1.4, web app verzija 4: akcija `history`. App je zove posle `today` (igrač) i kad staff otvori igrača;
  Progress, traka 7 dana i spremnost tada crtaju prave dane. Keš u localStorage `aekhub2:hist:<id>`.
- Referenca mosta je KAMP NEDELJA (W1_baza_kamp, nedeljni zbir), ne utakmica. Zato u živom režimu grafik
  „Week vs your camp week" ima zone 0.8 do 1.3x, tekuća nedelja je siva („Week in progress"), a kartica rekorda je
  „Top speed and camp week". Today merači pokazuju 100% = današnji cilj.
- Most radi za bilo koji datum: `plan_file_for` traži plan nedelje koji sadrži datum (W16, W17...). Na dan meča
  bira jedan red po igraču: MATCH ako je igrao 45+ minuta (dnevni_niz), inače dopunski trening.
- Top speed exposure: iznad svakog stubića stoji stvarna maksimalna brzina tog dana iz GPS-a (km/h), procenat je u odnosu
  na testirani maksimum (licni_max_brzina). Dan ispod 70% se crta na dnu skale, broj je i dalje tačan.
- Probna istorija: planovi i GPS za 21.10 do 03.11 su PRAVI (poslati kroz feed). Check-in, „Got it" i gym serije za
  Gacinovic, Majer i Relvas su SIMULIRANI (`seedDemoHistory`, 134 reda u Log, device „demo-history").
  PRE PRAVOG PILOTA pokrenuti `clearDemoHistory` u Apps Script editoru (briše samo demo redove).

## Šta Goran radi sam (ne može agent)

1. Google tabela + Apps Script po `backend/UPUTSTVO.md`, PIN-ovi igrača na listu Players.
2. URL web app-a u `config.js`, pa push.
3. Svako jutro: `python bridge/player_hub_feed.py --date <datum> --url <URL> --key <staff PIN>`
   (ili dugme u AEK HUB launcheru, još nije dodato), isto posle uvoza Catapult izvoza za rezultate.
4. Igračima link https://goranbasaric77-netizen.github.io/aek-player-hub/ i PIN; na iPhone-u Share > Add to Home Screen.

## Sledeći koraci (po prioritetu)

1. Dugme „Pošalji plan u hub" u AEK HUB launcheru (aek_hub.pyw) koje zove most za današnji datum.
2. (GOTOVO 04.11) Istorija uživo kroz akciju `history`. Ostaje: tab Week i staff tabela trend iz iste istorije.
3. Nedeljni plan u app-u (tab Week) iz mikrociklusa.
4. Aktivacija i mobility po igraču iz GPS plana (sada most daje grupnu aktivaciju, mobility prazno).
5. Push podsetnik u 07:30 (PWA push) ili WhatsApp poruka sa linkom.
6. Kad IT otvori hub.aekfc.gr: isti API kao PHP skript, promena samo `config.js`.

## Pravila vlasništva (da ne bude sukoba kao u GPS/GYM projektu)

- `index.html`, `sw.js`, `backend/`, `bridge/`: menja jedan agent u jednom trenutku. Pre veće izmene kopija
  `index_PRE_<NAZIV>_<datum>.html` u istom folderu.
- `config.js` i list Players u tabeli: Goran.
- GPS 2.5 folder: samo čitanje iz mosta, ništa se ne upisuje osim privremenog `hub_feed_<datum>.json` pri dry-run.
