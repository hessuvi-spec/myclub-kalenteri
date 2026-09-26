# myClub → Google-kalenteri

Tämä ohjelma siirtää jääkiekkojoukkueen tapahtumat myClubista Google-kalenteriin
kerran tunnissa. Se lisää uudet tapahtumat, päivittää siirretyt ja poistaa perutut.
Muihin kalenterisi tapahtumiin se ei koske.

**Tiedostot:**

| Tiedosto | Mitä se on |
|---|---|
| `synkronoi.py` | Itse ohjelma |
| `asetukset.py` | Suodatus, otsikot ja muut asetukset. Tätä saat muokata vapaasti |
| `requirements.txt` | Tarvittavat Python-kirjastot |
| `google-asennus.sh` | Googlen asetukset yhdellä kertaa (ajetaan Cloud Shellissä) |
| `.github/workflows/synkronoi.yml` | Kertoo GitHubille, että ohjelma ajetaan kerran tunnissa |

Käyttöönottoon menee noin 30–45 minuuttia. Tee vaiheet järjestyksessä.

---

## Vaihe 1: Hae myClubin kalenterilinkki

1. Kirjaudu myClubiin selaimella.
2. Avaa valikko oman nimesi vierestä ja valitse **Kalenteritilaukset** → **Uusi kalenteritilaus**.
3. Valitse pelaaja ja paina **Luo**.
4. Kopioi linkki talteen (esim. muistioon). **Pidä linkki salassa**, koska sillä näkee joukkueen aikataulun.

## Vaihe 2: Kokeile omalla koneella (valinnainen, mutta suositeltava)

1. Pura zip-tiedosto ja avaa `myclub-kalenteri`-kansio Resurssienhallinnassa.
2. Klikkaa osoiteriviä, kirjoita `cmd` ja paina Enter. Komentokehote aukeaa suoraan oikeaan kansioon.
3. Aja nämä kaksi komentoa:

```
pip install -r requirements.txt
python synkronoi.py --kokeile
```

4. Ohjelma kysyy linkkiä: liitä myClub-linkki hiiren oikealla napilla ja paina Enter.

(Jos `python` tai `pip` ei toimi, kokeile `py` ja `py -m pip`.)

Ohjelma näyttää tulevat tapahtumat ja kertoo, mitkä menisivät kalenteriin (`MUKAAN`)
ja mitkä jäisivät pois (`pois`). Googleen ei tässä vaiheessa kosketa.
Muokkaa `asetukset.py`-tiedostoa ja aja komento uudelleen, kunnes lista näyttää hyvältä.

## Vaihe 3: Tee uusi Google-kalenteri

1. Avaa [Google-kalenteri](https://calendar.google.com) tietokoneella.
2. Paina vasemmalla **Muut kalenterit** -kohdan vieressä **+** → **Luo uusi kalenteri**.
3. Anna nimeksi esim. **Jääkiekko** ja paina **Luo kalenteri**.

## Vaihe 4: Laita ohjelma GitHubiin

1. Tee tunnus osoitteessa [github.com](https://github.com), jos sinulla ei vielä ole.
2. Paina oikeasta yläkulmasta **+** → **New repository**. Anna nimeksi esim. `myclub-kalenteri`.
   Valitse **Public** (katso huomio alla) ja paina **Create repository**.
3. Paina **uploading an existing file** -linkkiä ja raahaa sinne kaikki tämän kansion tiedostot,
   **myös `.github`-kansio**. Paina **Commit changes**.
   - Jos `.github`-kansio ei siirry raahaamalla (piste nimen alussa voi piilottaa sen),
     paina **Add file** → **Create new file**, kirjoita nimeksi
     `.github/workflows/synkronoi.yml` ja liitä sisältö tiedostosta.
4. Kirjoita talteen repositorion koko nimi selaimen osoiteriviltä, esim. `hessuvi/myclub-kalenteri`.

> **Miksi Public?** Salaiset tiedot eivät ole koodissa vaan GitHubin salaisuuksissa,
> joita kukaan muu ei näe. Ilmaisella GitHub-tilillä ajastetut ajot eivät välttämättä
> käynnisty yksityisissä (Private) repositorioissa. Älä kuitenkaan kirjoita
> `asetukset.py`-tiedostoon mitään henkilökohtaista.

## Vaihe 5: Googlen asetukset (ilman avaintiedostoa)

Ohjelma kirjautuu Googleen ilman avaintiedostoa: Google luottaa suoraan sinun
GitHub-repositorioosi. Tämä on turvallisempaa, eikä se vaadi avaimen luontia.

1. Mene osoitteeseen [console.cloud.google.com](https://console.cloud.google.com).
2. Varmista yläreunan projektivalikosta, että oikea projekti on valittuna, ja kopioi sen
   **Project ID** (esim. `myclub-kalenteri-123456`).
3. Avaa **Cloud Shell**: oikean yläkulman `>_`-kuvake. Alareunaan aukeaa komentorivi.
4. Avaa `google-asennus.sh` Muistiolla ja muuta kaksi riviä:
   - `PROJEKTI=` → oma Project ID:si
   - `GITHUB_REPO=` → repositorion nimi vaiheesta 4
5. Kopioi **koko** tiedoston sisältö, liitä se Cloud Shelliin ja paina Enter.
   Jos Google kysyy lupaa (**Authorize**), hyväksy.
6. Lopuksi ruudulle tulee **VALMIS!** ja kaksi tietoa (`GOOGLE_WIF_PROVIDER` ja `GOOGLE_SERVICE_ACCOUNT`). Kopioi ne talteen.

## Vaihe 6: Anna robotille lupa kalenteriin

1. Google-kalenterissa: vie hiiri **Jääkiekko**-kalenterin päälle → kolme pistettä → **Asetukset ja jakaminen**.
2. Kohdassa **Jaa tiettyjen käyttäjien tai ryhmien kanssa** paina **Lisää käyttäjiä ja ryhmiä**.
3. Liitä palvelutilin osoite (`kalenterirobotti@...iam.gserviceaccount.com`) ja valitse
   oikeudeksi **Tee muutoksia tapahtumiin** → **Lähetä**.
4. Vieritä samalla sivulla kohtaan **Integroi kalenteri** ja kopioi **Kalenterin tunnus**
   (näyttää tältä: `abc123...@group.calendar.google.com`).

**Muistutukset:** Samalta asetussivulta löytyy kohta **Tapahtumailmoitukset**. Lisää sinne
haluamasi muistutukset (esim. 2 tuntia ja 30 minuuttia ennen). Ne tulevat automaattisesti
kaikkiin ohjelman lisäämiin tapahtumiin.

## Vaihe 7: Lisää salaisuudet GitHubiin

Repositoriossa: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Lisää nämä neljä:

| Name | Secret |
|---|---|
| `MYCLUB_ICS_URL` | myClubin kalenterilinkki (vaihe 1) |
| `GOOGLE_CALENDAR_ID` | Kalenterin tunnus (vaihe 6) |
| `GOOGLE_WIF_PROVIDER` | Cloud Shellin tulostama `projects/.../providers/github-repo` (vaihe 5) |
| `GOOGLE_SERVICE_ACCOUNT` | Palvelutilin osoite `kalenterirobotti@...iam.gserviceaccount.com` (vaihe 5) |

## Vaihe 8: Käynnistä ensimmäinen ajo

1. Repositoriossa: välilehti **Actions**. Jos GitHub kysyy, paina **I understand my workflows, go ahead and enable them**.
2. Valitse vasemmalta **myClub -> Google-kalenteri** → **Run workflow** → **Run workflow**.
3. Hetken päästä ajo muuttuu vihreäksi ✅. Klikkaamalla sitä näet, mitä ohjelma teki
   (esim. `+ Lisätty: 🏒 Harjoitus (01.10. klo 17:00)`).
4. Tarkista Google-kalenteri. Tästä eteenpäin GitHub ajaa ohjelman itse kerran tunnissa.

---

## Hyvä tietää

- **Asetusten muokkaus:** Muokkaa `asetukset.py`-tiedostoa suoraan GitHubissa (kynä-ikoni).
  Muutos tulee voimaan seuraavalla ajolla.
- **Ajastus voi viivästyä:** GitHub ei aina aja ohjelmaa täsmälleen ajallaan, vaan joskus
  viiveellä. Se on normaalia.
- **Jos repositoriossa ei tapahdu mitään 60 päivään,** GitHub voi pysäyttää ajastuksen ja
  lähettää siitä sähköpostia. Silloin mene **Actions**-välilehdelle ja paina **Enable workflow**.
  Pienikin muutos tiedostoihin nollaa laskurin.
- **Punainen ❌ ajo:** Klikkaa sitä ja lue virheilmoitus. Yleisimmät syyt:
  - Salaisuuden nimi kirjoitettu väärin.
  - Kalenteria ei ole jaettu palvelutilille (vaihe 6).
  - `GITHUB_REPO` kirjoitettu eri tavalla kuin repositorion todellinen nimi (vaihe 5).
  - Googlen asetukset eivät ole vielä voimassa: odota 5 minuuttia ja aja uudelleen.
- **Turvatoimi:** Jos myClubista ei jostain syystä tule yhtään tapahtumaa, ohjelma ei tee
  kalenteriin mitään, jottei se vahingossa tyhjennä sitä.
- **Perheenjäsenet:** Jaa Jääkiekko-kalenteri heille Google-kalenterin jakoasetuksista
  (oikeus **Näe kaikki tapahtuman tiedot**), niin kaikilla on sama aikataulu.
