# AEK Player Hub: zadnji deo na Google tabeli (jednokratno podešavanje, 15 minuta)

Igrači koriste app sa telefona. Sve što urade (check-in, serije, potvrde) upisuje se u jednu Google tabelu,
a app iz iste tabele čita dnevne ciljeve. Tabelu i skript praviš jednom, na klupskom ili svom Google nalogu.

## 1. Napravi tabelu

1. Otvori https://sheets.new (nalog na kome želiš da stoje podaci igrača).
2. Nazovi tabelu **AEK Player Hub**.

## 2. Ubaci skript

1. U tabeli: meni **Extensions > Apps Script**.
2. Obriši sve iz fajla `Code.gs` i nalepi ceo sadržaj fajla `backend/Code.gs` iz hub foldera.
3. Sačuvaj (ikona diskete ili Ctrl+S).
4. Gore izaberi funkciju **setup** pa klikni **Run**. Google će tražiti dozvolu: Review permissions > izaberi nalog >
   Advanced > Go to AEK Player Hub (unsafe) > Allow. To je normalno za sopstveni skript.
5. Vrati se u tabelu: sada ima listove Players, Plan, Results, Log, Tokens i Today.

## 3. Upiši igrače i PIN-ove

Na listu **Players** stoje probni redovi. Ispravi ih:

| id | name | pin | role | active |
|----|------|-----|------|--------|
| __staff | Performance staff | tvoj PIN | staff | 1 |
| koita | Abubakary Koita | 4 cifre | player | 1 |
| ... | ... | ... | player | 1 |

- `id` mora da bude isti kao u app-u (kolona ROSTER u index.html: koita, varga, alexiou, kutesa, kaloskamis, vida, relvas,
  sahabo, moukoudi, kairinen, ariaga, rota, majer, jovic, georgiev, gacinovic, vitalis, likogiannis, zubkov, mantalos,
  marin, zine, pilios, joaomario, argyriou, christakopoulos, strakosha, brignoli, balamotis).
- Staff PIN je ujedno i ključ kojim most iz GPS 2.5 šalje planove (vidi bridge/player_hub_feed.py).
- `active` 0 isključuje igrača bez brisanja reda.

## 4. Objavi web app

1. U Apps Script editoru: **Deploy > New deployment**.
2. Tip: **Web app**. Description: `hub v1`. Execute as: **Me**. Who has access: **Anyone**.
3. **Deploy**, pa kopiraj **Web app URL** (počinje sa `https://script.google.com/macros/s/...`).

## 5. Upiši URL u app

U hub folderu otvori `config.js` i upiši URL:

```
window.AEK_SYNC = { url: "https://script.google.com/macros/s/.../exec" };
```

Sačuvaj i objavi hub (add, commit, push). Od tog trenutka app radi uživo: PIN se proverava u tabeli,
sve što igrači urade stiže na list **Log**, a tvoj pregled je tab **Team** u app-u ili list **Today** u tabeli
(meni **AEK Hub > Osveži Today**).

## Kad menjaš skript

Posle izmene u `Code.gs`: **Deploy > Manage deployments > olovka > Version: New version > Deploy**.
URL ostaje isti, app ne treba dirati.

## Šta gde piše

- **Plan**: jedan red po datumu i igraču (puni ga most, može i ručno). Ako za igrača nema reda za današnji dan,
  app mu pokazuje „Plan not published yet" i samo check-in.
- **Results**: GPS rezultat posle treninga (td, hsr, spr, vmax). Puni ga most. Čim stigne, zeleni prsten se popuni.
- **Log**: sve akcije igrača sa vremenom (open, checkin, gym, mob, ack). Ne briši, to je istorija.
- **Tokens**: prijave uređaja. Obriši red da izbaciš telefon.
- **Today**: tvoj brzi pregled po igraču, pravi se iz Log-a na klik.

## Privatnost

Tabelu deli samo sa staffom. Wellness odgovori igrača su lični podaci, pa tabela ne ide trećim licima.
