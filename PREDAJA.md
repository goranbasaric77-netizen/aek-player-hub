# AEK Player Hub: predaja stanja (04.11.2026, dopuna 14:50)

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
Nova verzija = izmena `index.html`, podići `CACHE` u sw.js (sledeće slovo istog dana, npr. `2026-11-04j`, novi dan = novi datum),
pa `git add -A && git commit -m "..." && git push`. CACHE ide u ISTI commit, inače telefoni ostaju na staroj verziji.
Kad agent nema komandnu liniju na računaru, on menja fajlove u folderu, a Goran pokreće git komandu koju agent ispiše.

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
- (ZAMENJENO 04.11 15:00, Goran: „dijagram vs camp je bezveze, treba x utakmica") Referenca je SOPSTVENA UTAKMICA
  per 90 iz mec_referenca.csv (kao Sidro u GPS 2.5). Grafik „Week vs your own match": stubići = urađeno u nedelji
  (trening + mečevi) u × utakmice, isprekidana linija = plan nedelje igrača iz motora (engine.load_plan_kompletan_sums,
  isti kao Sidro), boja = urađeno/plan (90 % zeleno, 70 % žuto, ispod 70 % ili preko 115 % crveno), tekuća nedelja siva
  sa planom do sada. Podaci u extra_json.weeks (poslednjih 5 nedelja sa plan_kompletan fajlom), ref_src/ref_matches.
  ref_td/hsr/spr u Plan listu su sada per 90 (kartica „Top speed and your match"). Today merači pokazuju 100% = današnji cilj.
- Most radi za bilo koji datum: `plan_file_for` traži plan nedelje koji sadrži datum (W16, W17...). Na dan meča
  bira jedan red po igraču: MATCH ako je igrao 45+ minuta (dnevni_niz), inače dopunski trening.
- Top speed exposure: iznad svakog stubića stoji stvarna maksimalna brzina tog dana iz GPS-a (km/h), procenat je u odnosu
  na testirani maksimum (licni_max_brzina). Dan ispod 70% se crta na dnu skale, broj je i dalje tačan.
- Probna istorija: planovi i GPS za 21.10 do 03.11 su PRAVI (poslati kroz feed). Check-in, „Got it" i gym serije za
  Gacinovic, Majer i Relvas su SIMULIRANI (`seedDemoHistory`, 134 reda u Log, device „demo-history").
  PRE PRAVOG PILOTA pokrenuti `clearDemoHistory` u Apps Script editoru (briše samo demo redove).

## Istina iz GPS 2.5 (04.11.2026 popodne, most v2 + app + Code.gs 1.5)

Pravilo: u živom režimu igrač vidi SAMO ono što stoji u GPS 2.5 motoru. Nema izmišljenih sati, protivnika ni tekstova.

- `bridge/player_hub_feed.py` v2 uvozi `gym_dpp` iz foldera app-a i koristi iste funkcije kao Daily Player Plan PDF
  (`_plan_red`, `_ciljevi`, `_why`, `_gym_redovi`, `_brzina`, `_prilagodi_za_pdf`), pa hub i PDF kažu isto.
  Gym dolazi iz `gym/gym_state.json` (ne više iz zastarelog `gym_export_latest.json`), sa zamenama po kodovima i kg iz 1RM.
  Aktivacija i mobility = blokovi iste sesije. Sat sesije: iz napomene mikrociklusa; za prošle dane iz imena Catapult
  exporta (16:23); kad sat nije upisan piše „(time tbc)“ ili „(morning)/(afternoon)“, nikad izmišljen sat.
  Dan meča: PRE uvoza meča svi dobijaju MATCH red (sastav se ne otkriva), POSLE uvoza ko je igrao 45+ ostaje na meču
  sa svojim minutima, ostali dobijaju top-up red i rezultat. Status POVREDA/REHAB/BOLEST -> „Out of the team plan“ sa EN
  tekstom iz status_igraca. Nova kolona Plan lista `extra_json`: sat sesije, da li je sat poznat, dan meča, minuti,
  sledeći meč (datum, sat, protivnik, takmičenje, dom/gost), tekst nedelje i 7 dana nedelje za tab Week, vreme objave.
- `backend/Code.gs` 1.5: `extra_json` u SHEETS.Plan, `planOut` vraća `extra`, `ensureHeaders("Plan")` dopisuje
  zaglavlje nove kolone pri prvom feed-u. POSLE PUSH-A: zalepiti Code.gs u Apps Script editor, Deploy > Manage
  deployments > olovka > New version > Deploy (URL ostaje).
- `index.html`: sat koraka 1/2/3, odbrojavanje i kartica sledećeg meča, sati vremenske prognoze, oznaka „published“
  i tab Week dolaze iz `extra`; rezultat sesije se prikazuje i uživo (ne samo u skici); dan bez gym-a nema lažni
  „Session complete“; „perfect days“ broji samo dane sa planom; staff „gym complete“ broji samo igrače sa planiranim
  gym-om. Kopija: `index_PRE_ISTINA_20261104.html`, `bridge/player_hub_feed_PRE_ISTINA_20261104.py`,
  `backend/Code_PRE_ISTINA_20261104.gs`.
- GPS strana: `data/dpp_why.csv` dobio tekstove za MD+1/-2_KOMP_LAKA, MD+1_AKTIVNI_OPORAVAK, MD-1/MD-2_IZMEDJU_2M,
  MD+2_OPORAVAK, MD+2_IZMEDJU_2M, TOPUP, MD-3_POVRATAK, MD-1_NE_IGRAJU (ranije je most za te dane vraćao pogrešan
  tekst pune kompenzacije). Koristi ih i DPP PDF.
- Na klik: dugme „POŠALJI PLAN U PLAYER HUB“ u AEK HUB launcheru (aek_hub.pyw) zove most za današnji datum; isto dugme
  ponovo posle uvoza Catapult exporta (šalje Results i na dan meča prebacuje igrače bez 45 min na top-up).
- Probano na mock serveru sa pravim paketima za 02, 03, 04 i 06.11 (Relvas, Kaloskamis, staff tabela): bez JS grešaka.

## Stanje objave (04.11.2026, 15:30)

- Code.gs 1.5 je u Apps Script-u, deployment verzija 5 (URL isti). `/exec` GET vraća `"version":"1.5"`.
- Feed poslat za 02.11, 03.11 i 04.11 (Plan 26 + 26 + 26 redova sa `extra_json`, Results 14 za 02.11 i 24 za 03.11).
  04.11: svi dobijaju MATCH red Real Madrid 19:45 (sastav se ne otkriva).
- Na listu Plan za 04.11 ostalo je 14 starih redova (jutarnji feed, „Match 11:00“) iznad novih. Ne smeta: API uvek
  čita poslednji red za (datum, igrač), a sledeći feed ažurira nove redove. Mogu se ručno obrisati.
- Ostaje Goranu: `git add -A`, `git commit`, `git push` u folderu AEK_PLAYER_HUB (agent nema GitHub prijavu).
  Dok push ne prođe, živi sajt je stara verzija app-a i ne čita `extra` (tab Week, sat meča, grafik x utakmica).
- Posle meča: obrisati ili prepisati privremeni `data/minuti_2026-11-04.csv` u GPS 2.5, uvesti Catapult export
  meča, pa ponovo „POŠALJI PLAN U PLAYER HUB“ za 04.11 (igrači bez 45 min prelaze na top-up i dobijaju rezultat).

- 04.11 16:30, verzija 2026-11-04k: app pri svakom otvaranju i povratku na ekran proverava novi service worker i
  kad nova verzija preuzme, sam se jednom osveži. Oznaka verzije stoji ispod PIN-a na ekranu za prijavu
  („Version …“, menja se sa svakim izdanjem zajedno sa CACHE u sw.js). Kopija: `index_PRE_UPDATE_20261104.html`.

- 04.11 18:00, verzija 2026-11-04l (Goranova odluka): svi grafici prate MIKROCIKLUS ponedeljak do nedelje, ne
  poslednjih N dana. Prstenovi, teren done vs plan, gym, readiness: tekuća nedelja (W18, Mon 2 Nov to Sun 8 Nov),
  budući dani prazni/bledi. Top speed: prethodna + tekuća nedelja (W17 + W18) sa crtom između. Weekly load stubovi
  nose oznaku nedelje (W16, W17, W18). Broj nedelje se čita iz extra_json.week_label. Kopija: `index_PRE_MIKRO_20261104.html`.

## Šta Goran radi sam (ne može agent)

1. Google tabela + Apps Script po `backend/UPUTSTVO.md`, PIN-ovi igrača na listu Players.
2. URL web app-a u `config.js`, pa push.
3. Svako jutro dugme „POŠALJI PLAN U PLAYER HUB“ u AEK HUB launcheru (ili `python bridge/player_hub_feed.py --date <datum>
   --url <URL> --key <staff PIN>`), isto posle uvoza Catapult izvoza za rezultate.
4. Igračima link https://goranbasaric77-netizen.github.io/aek-player-hub/ i PIN; na iPhone-u Share > Add to Home Screen.

## Sledeći koraci (po prioritetu)

1. (GOTOVO) Dugme „Pošalji plan u hub" u AEK HUB launcheru.
2. (GOTOVO 04.11) Istorija uživo kroz akciju `history`. Ostaje: staff tabela trend iz iste istorije.
3. (GOTOVO 04.11) Tab Week iz mikrociklusa (extra_json.week).
4. (GOTOVO 04.11) Aktivacija i mobility po igraču iz gym sesije; ostaje leteći sprint kao posebna stavka uz teren.
5. Push podsetnik u 07:30 (PWA push) ili WhatsApp poruka sa linkom.
6. Kad IT otvori hub.aekfc.gr: isti API kao PHP skript, promena samo `config.js`.

## Pravila vlasništva (da ne bude sukoba kao u GPS/GYM projektu)

- `index.html`, `sw.js`, `backend/`, `bridge/`: menja jedan agent u jednom trenutku. Pre veće izmene kopija
  `index_PRE_<NAZIV>_<datum>.html` u istom folderu.
- `config.js` i list Players u tabeli: Goran.
- GPS 2.5 folder: samo čitanje iz mosta, ništa se ne upisuje osim privremenog `hub_feed_<datum>.json` pri dry-run.

- 05.11 23:15, verzija 2026-11-05m (Goran: „uradi mi samo za staff"): staff može da gleda JUČE / DANAS / SUTRA. U Team heroju
  tri dugmeta (Yesterday, Today, Tomorrow); `setStaffDay(off)` pomera `TODAY`/`TK` (sada `let`, pravi dan ostaje u `TODAY0`),
  ponovo vuče `team` za taj datum i otvara igrača za taj datum (plan, rezultat, istorija). Igrač UVEK vidi pravi današnji dan:
  `enter(id)` vraća pomak na 0. Igrači ne vide sutra (Goranova odluka). Kopija: `index_PRE_STAFFDATE_20261105.html`.
  Feed za sutra treba poslati uveče da bi „Tomorrow" imao sadržaj (AEK_GPS_APP\Posalji_Hub_04_i_06.bat šalje 04, 05, 06.11).
