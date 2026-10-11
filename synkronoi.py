"""
myClub -> Google-kalenteri -synkronointi
========================================

Mitä tämä ohjelma tekee:
  1. Hakee tapahtumat myClubin kalenterilinkistä (iCal-muoto).
  2. Suodattaa ja muotoilee ne asetukset.py-tiedoston mukaan.
  3. Vertaa niitä Google-kalenterissa jo oleviin tapahtumiin ja
     - lisää uudet
     - päivittää muuttuneet (esim. siirretty aika)
     - poistaa perutut / myClubista poistetut

Kokeilu omalla koneella ilman Googlea (tulostaa vain tapahtumat):
    python synkronoi.py --kokeile
(ohjelma kysyy linkin, liitä se ja paina Enter)
"""

import datetime as dt
import hashlib
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar

import asetukset

TZ = ZoneInfo(asetukset.AIKAVYOHYKE)

# Tällä merkinnällä tunnistetaan Google-kalenterista ne tapahtumat,
# jotka tämä ohjelma on tehnyt. Muihin tapahtumiin ei kosketa.
LAHDE = "myclub-synkka"


# ------------------------------------------------------------
# 1. Tapahtumien haku myClubista
# ------------------------------------------------------------

def hae_myclub_tapahtumat(url):
    """Lataa iCal-tiedoston ja palauttaa listan tapahtumia (sanakirjoina)."""
    # Puhelimen "webcal://"-linkki toimii kuten https://
    url = url.strip().strip('"').strip("'")
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.startswith("http"):
        sys.exit(f"Virhe: '{url}' ei näytä linkiltä. Linkin pitää alkaa https:// tai webcal://")

    try:
        vastaus = requests.get(url, timeout=30)
        vastaus.raise_for_status()  # virhe, jos lataus epäonnistui
    except requests.RequestException as virhe:
        sys.exit(f"Virhe: myClub-linkin lataus epäonnistui.\n{virhe}")
    try:
        kalenteri = Calendar.from_ical(vastaus.content)
    except ValueError:
        sys.exit("Virhe: linkin takaa ei tullut kalenteria. Tarkista, että kopioit "
                 "myClubin Kalenteritilaukset-sivulta koko linkin.")

    # Ryhmitellään tapahtumat UID:n (tapahtuman tunnisteen) mukaan.
    # myClub voi antaa saman UID:n monelle eri tapahtumalle (esim. kaikki
    # torstain harjoitukset), joten niitä ei saa yhdistää yhdeksi.
    ryhmat = {}
    for osa in kalenteri.walk("VEVENT"):
        ryhmat.setdefault(str(osa.get("UID", "")), []).append(osa)

    nyt = dt.datetime.now(TZ)
    ikkuna_alku = nyt - dt.timedelta(days=1)
    ikkuna_loppu = nyt + dt.timedelta(days=asetukset.PAIVIA_ETEENPAIN + 1)

    kerrat = []        # (osa, uid, onko_toistuva)
    for uid, osat in ryhmat.items():
        if any("RRULE" in o or "RDATE" in o for o in osat):
            # Oikea toistuva tapahtuma ("joka torstai"): puretaan yksittäisiksi kerroiksi
            apukalenteri = Calendar()
            for o in osat:
                apukalenteri.add_component(o)
            for o in recurring_ical_events.of(apukalenteri).between(ikkuna_alku, ikkuna_loppu):
                kerrat.append((o, uid, True))
        else:
            # Tavalliset tapahtumat otetaan sellaisenaan, myös jos UID on sama
            for o in osat:
                kerrat.append((o, uid, len(osat) > 1))

    tapahtumat = []
    for osa, uid, toistuva in kerrat:
        alku = osa.decoded("DTSTART")
        if "DTEND" in osa:
            loppu = osa.decoded("DTEND")
        elif "DURATION" in osa:
            loppu = alku + osa.decoded("DURATION")
        else:
            loppu = alku + dt.timedelta(hours=1)

        avain = uid
        if toistuva:
            # Jokainen toistokerta tarvitsee oman tunnisteen. Käytetään kerran
            # alkuperäistä aikaa, jotta siirretty harjoitus päivittyy eikä tuplaannu.
            alkuperainen = osa.get("RECURRENCE-ID")
            alkuperainen = alkuperainen.dt if alkuperainen else alku
            avain = f"{uid}|{aikaleimaksi(alkuperainen).isoformat()}"

        tapahtumat.append({
            "uid": avain,
            "nimi": str(osa.get("SUMMARY", "")).strip(),
            "paikka": str(osa.get("LOCATION", "")).strip(),
            "kuvaus": str(osa.get("DESCRIPTION", "")).strip(),
            "tila": str(osa.get("STATUS", "")).upper(),
            "alku": alku,
            "loppu": loppu,
        })
    return tapahtumat


def aikaleimaksi(arvo):
    """Muuttaa ajan aina aikavyöhykkeelliseksi datetimeksi vertailuja varten.
    Koko päivän tapahtumilla (pelkkä päivämäärä) käytetään keskiyötä."""
    if isinstance(arvo, dt.datetime):
        if arvo.tzinfo is None:
            return arvo.replace(tzinfo=TZ)
        return arvo.astimezone(TZ)  # esim. UTC-aika -> Suomen aika
    return dt.datetime.combine(arvo, dt.time(0, 0), tzinfo=TZ)


# ------------------------------------------------------------
# 2. Suodatus ja muotoilu
# ------------------------------------------------------------

def sisaltaa_jonkin(teksti, sanat):
    teksti = teksti.lower()
    return any(sana.lower() in teksti for sana in sanat)


def kuuluu_mukaan(tapahtuma, nyt, loppuraja):
    """True, jos tapahtuma siirretään Google-kalenteriin."""
    if tapahtuma["tila"] == "CANCELLED":
        return False
    # Vain tulevat (tai parhaillaan käynnissä olevat) tapahtumat
    if aikaleimaksi(tapahtuma["loppu"]) <= nyt:
        return False
    if aikaleimaksi(tapahtuma["alku"]) >= loppuraja:
        return False
    nimi = tapahtuma["nimi"]
    # Nämä otetaan aina mukaan, vaikka nimessä olisi myös jokin pois-sana
    aina_mukaan = getattr(asetukset, "AINA_MUKAAN_JOS_NIMESSA", [])
    if aina_mukaan and sisaltaa_jonkin(nimi, aina_mukaan):
        return True
    if asetukset.MUKAAN_JOS_NIMESSA and not sisaltaa_jonkin(nimi, asetukset.MUKAAN_JOS_NIMESSA):
        return False
    if asetukset.POIS_JOS_NIMESSA and sisaltaa_jonkin(nimi, asetukset.POIS_JOS_NIMESSA):
        return False
    return True


def muotoile_otsikko(nimi):
    for poistettava in asetukset.POISTA_OTSIKOSTA:
        nimi = nimi.replace(poistettava, "")
    nimi = " ".join(nimi.split())  # siivotaan ylimääräiset välilyönnit

    alku = asetukset.OTSIKON_ALKU_MUUTEN
    for hakusana, merkki in asetukset.OTSIKON_ALKU.items():
        if hakusana.lower() in nimi.lower():
            alku = merkki
            break
    return f"{alku} {nimi}".strip()


def aika_googlelle(arvo):
    """Google haluaa koko päivän tapahtumille 'date' ja muille 'dateTime'."""
    if isinstance(arvo, dt.datetime):
        return {"dateTime": aikaleimaksi(arvo).isoformat(), "timeZone": asetukset.AIKAVYOHYKE}
    return {"date": arvo.isoformat()}


def tunniste(uid):
    """Lyhyt, pysyvä tunniste myClub-tapahtumalle."""
    return hashlib.sha1(uid.encode("utf-8")).hexdigest()


# ------------------------------------------------------------
# 2b. Leijonat TV -linkit peleihin
# ------------------------------------------------------------

LEIJONAT_PELIT_URL = "https://tulospalvelu.leijonat.fi/helpers/getgames"


def ilmoita(tyyppi, viesti):
    """Tulostaa viestin. GitHubissa se näkyy myös ajon yhteenvedossa (Annotations)."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        siivottu = viesti.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{tyyppi} title=myClub-botti::{siivottu}")
    else:
        print(viesti)


PELIT_TIEDOSTO = "pelit.json"


def hae_leijonat_pelit_netista():
    """Hakee tulevat pelit suoraan Leijonien tulospalvelusta.
    Palauttaa None, jos haku ei onnistu (esim. palvelu estää GitHubin)."""
    pelit = []
    tanaan = dt.datetime.now(TZ).date().isoformat()
    for sarja_url in getattr(asetukset, "LEIJONAT_SARJAT", []):
        kysely = parse_qs(urlparse(sarja_url).query)
        try:
            parametrit = {
                "dwl": 0, "season": kysely["season"][0], "subSerieId": kysely["ssid"][0],
                "teamid": 0, "districtid": 0, "gamedays": 2, "dog": tanaan, "levelid": -1,
            }
            vastaus = requests.get(LEIJONAT_PELIT_URL, params=parametrit, timeout=20, headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": sarja_url,
            })
            vastaus.raise_for_status()
            for taso in vastaus.json():
                pelit.extend(taso.get("Games", []))
        except Exception as virhe:
            print(f"Leijonien tulospalvelun haku ei onnistunut: {virhe}")
            return None
    return pelit


def hae_leijonat_pelit():
    """Hakee pelit netistä. Jos se ei onnistu, käytetään tiedostoa pelit.json,
    jonka voi päivittää omalla koneella ohjelmalla paivita_pelit.py."""
    if not getattr(asetukset, "LEIJONAT_SARJAT", []):
        return []
    pelit = hae_leijonat_pelit_netista()
    if pelit is not None:
        print(f"Pelit haettu suoraan tulospalvelusta ({len(pelit)} kpl).")
        return pelit
    if os.path.exists(PELIT_TIEDOSTO):
        with open(PELIT_TIEDOSTO, encoding="utf-8") as f:
            pelit = json.load(f)
        print(f"Pelit luettu tiedostosta {PELIT_TIEDOSTO} ({len(pelit)} kpl).")
        return pelit
    ilmoita("warning", "Leijonat TV -linkkejä ei lisätty: tulospalvelu ei vastannut "
                       f"eikä tiedostoa {PELIT_TIEDOSTO} löytynyt.")
    return []


def pelin_tv_linkit(peli):
    """Tekee pelin lähetyslinkit samalla tavalla kuin tulospalvelun oma sivu."""
    leijonat_tv = (f"https://www.leijonat.tv/fi/game?ext-id={peli['GameID']}"
                   f"&season-id={peli['Season']}")
    linkit = []
    lahteet = peli.get("StreamSources") or []
    for lahde in lahteet:
        url = lahde.get("StreamUrl") or ""
        if not url and lahde.get("IsDefault"):
            url = leijonat_tv
        if url:
            linkit.append((lahde.get("SourceName") or "Lähetys", url))
    if not lahteet:
        if peli.get("LiveURL"):
            linkit.append(("Lähetys", peli["LiveURL"]))
        elif peli.get("LiveFeedSource") == 4 and peli.get("OnlyStreamStorage") == 1:
            linkit.append(("Leijonat TV", leijonat_tv))
    return linkit


def joukkue_nimessa(joukkue, nimi):
    """Onko joukkueen nimi (esim. 'KHT Hokki Sininen') tapahtuman nimessä?
    Etuliitteet kuten 'KHT ' saa jättää pois."""
    vaihtoehdot = [joukkue]
    for etuliite in getattr(asetukset, "LEIJONAT_POISTA_ETULIITE", []):
        if joukkue.lower().startswith(etuliite.lower()):
            vaihtoehdot.append(joukkue[len(etuliite):])
    for v in vaihtoehdot:
        v = " ".join(v.lower().split())
        if v and re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", nimi):
            return True
    return False


def etsi_tapahtuman_pelit(tapahtuma, pelit):
    """Etsii myClub-tapahtumaa vastaavat pelit: sama päivä, joukkueen nimi
    tapahtuman nimessä ja pelin alkuaika tapahtuman aikana."""
    if not isinstance(tapahtuma["alku"], dt.datetime):
        return []
    alku = aikaleimaksi(tapahtuma["alku"])
    loppu = aikaleimaksi(tapahtuma["loppu"])
    nimi = " ".join(tapahtuma["nimi"].lower().split())

    ehdokkaat = []          # pelit, joiden kellonaika sopii tapahtumaan
    samana_paivana = []     # varalla: sama päivä ja joukkue, kellonaika ei täsmää
    for peli in pelit:
        try:
            paiva = dt.datetime.strptime(peli["GameDate"], "%d.%m.%Y").date()
        except (KeyError, ValueError):
            continue
        if paiva != alku.date():
            continue
        osumat = sum(joukkue_nimessa(peli.get(k) or "", nimi)
                     for k in ("HomeTeamAbbrv", "AwayTeamAbbrv"))
        if osumat == 0:
            continue
        samana_paivana.append((osumat, peli))
        if peli.get("GameTime"):
            tunnit, minuutit = peli["GameTime"].split(":")[:2]
            pelin_alku = alku.replace(hour=int(tunnit), minute=int(minuutit), second=0)
            if not (alku - dt.timedelta(minutes=30) <= pelin_alku <= loppu):
                continue
        ehdokkaat.append((osumat, peli))
    if not ehdokkaat:
        # Pelin aika on voinut muuttua tai se on vielä merkitty "06:00"-tyyppisellä
        # paikkamerkillä, joten tyydytään saman päivän otteluun.
        ehdokkaat = samana_paivana
    if not ehdokkaat:
        return []
    paras = max(o for o, _ in ehdokkaat)
    return [p for o, p in ehdokkaat if o == paras]


def lisaa_tv_linkit(tapahtumat, pelit):
    """Lisää jokaiseen myClub-tapahtumaan kentän 'tv' (tekstirivit linkkeineen)."""
    for t in tapahtumat:
        rivit = []
        for peli in etsi_tapahtuman_pelit(t, pelit):
            for lahde, url in pelin_tv_linkit(peli):
                aika = (peli.get("GameTime") or "")[:5]
                ottelu = f"{peli.get('HomeTeamAbbrv')} - {peli.get('AwayTeamAbbrv')}"
                rivit.append(f"📺 {lahde}: {ottelu}" + (f" klo {aika}" if aika else "") + f"\n{url}")
        t["tv"] = "\n\n".join(rivit)
    linkillisia = sum(1 for t in tapahtumat if t["tv"])
    if getattr(asetukset, "LEIJONAT_SARJAT", []):
        ilmoita("notice", f"Leijonat TV: {len(pelit)} tulevaa peliä tiedossa, "
                          f"linkki lisätty {linkillisia} kalenterimerkintään.")


def tee_google_tapahtuma(tapahtuma):
    """Muuttaa myClub-tapahtuman Google-kalenterin muotoon."""
    runko = {
        "summary": muotoile_otsikko(tapahtuma["nimi"]),
        "location": tapahtuma["paikka"],
        "description": "\n\n".join(x for x in (tapahtuma.get("tv", ""), tapahtuma["kuvaus"]) if x),
        "start": aika_googlelle(tapahtuma["alku"]),
        "end": aika_googlelle(tapahtuma["loppu"]),
        # Muistutukset tulevat kalenterin omista oletusasetuksista
        "reminders": {"useDefault": True},
    }
    # Sormenjälki sisällöstä: tällä tiedetään, onko tapahtuma muuttunut
    sormenjalki = hashlib.sha1(json.dumps(runko, sort_keys=True).encode("utf-8")).hexdigest()
    runko["extendedProperties"] = {
        "private": {
            "lahde": LAHDE,
            "myclub_id": tunniste(tapahtuma["uid"]),
            "sormenjalki": sormenjalki,
        }
    }
    return runko


# ------------------------------------------------------------
# 3. Google-kalenteri
# ------------------------------------------------------------

def yhdista_googleen():
    """Kirjautuu Googleen palvelutilin tunnuksilla."""
    import google.auth
    import google.auth.exceptions
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    avain_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    oikeudet = ["https://www.googleapis.com/auth/calendar.events"]
    if avain_json:
        # Vaihtoehto A: palvelutilin avain (json) GitHubin salaisuutena
        tunnukset = service_account.Credentials.from_service_account_info(
            json.loads(avain_json), scopes=oikeudet)
    elif os.path.exists("palvelutili.json"):
        tunnukset = service_account.Credentials.from_service_account_file(
            "palvelutili.json", scopes=oikeudet)
    else:
        # Vaihtoehto B: avaimeton kirjautuminen (GitHubin google-github-actions/auth
        # -vaihe tekee tunnukset valmiiksi, ja ne löytyvät automaattisesti)
        try:
            tunnukset, _ = google.auth.default(scopes=oikeudet)
        except google.auth.exceptions.DefaultCredentialsError:
            sys.exit("Virhe: Google-tunnuksia ei löytynyt. Tarkista GitHubin salaisuudet.")
    return build("calendar", "v3", credentials=tunnukset, cache_discovery=False)


def hae_google_tapahtumat(palvelu, kalenteri_id, nyt, loppuraja):
    """Hakee ne Google-tapahtumat, jotka tämä ohjelma on aiemmin tehnyt."""
    tapahtumat = []
    sivu = None
    while True:
        vastaus = palvelu.events().list(
            calendarId=kalenteri_id,
            privateExtendedProperty=f"lahde={LAHDE}",
            timeMin=nyt.isoformat(),
            timeMax=loppuraja.isoformat(),
            singleEvents=True,
            maxResults=250,
            pageToken=sivu,
        ).execute()
        tapahtumat.extend(vastaus.get("items", []))
        sivu = vastaus.get("nextPageToken")
        if not sivu:
            return tapahtumat


def nayta_aika(runko):
    """Tulostusta varten: '01.10. klo 17:00' tai '10.10.' """
    alku = runko["start"]
    if "dateTime" in alku:
        return dt.datetime.fromisoformat(alku["dateTime"]).strftime("%d.%m. klo %H:%M")
    return dt.date.fromisoformat(alku["date"]).strftime("%d.%m.")


def synkronoi(palvelu, kalenteri_id, myclub_tapahtumat, nyt, loppuraja):
    """Vertaa myClubin ja Googlen tapahtumia ja tekee tarvittavat muutokset."""
    # Mitä Googlessa pitäisi olla: {myclub_id: tapahtuman tiedot}
    halutut = {}
    for t in myclub_tapahtumat:
        if kuuluu_mukaan(t, nyt, loppuraja):
            runko = tee_google_tapahtuma(t)
            halutut[runko["extendedProperties"]["private"]["myclub_id"]] = runko

    # Mitä Googlessa nyt on: {myclub_id: google-tapahtuma}
    nykyiset = {}
    for g in hae_google_tapahtumat(palvelu, kalenteri_id, nyt, loppuraja):
        mid = g.get("extendedProperties", {}).get("private", {}).get("myclub_id")
        if mid in nykyiset:
            # Tuplakappale (esim. keskeytyneestä ajosta) -> poistetaan
            palvelu.events().delete(calendarId=kalenteri_id, eventId=g["id"]).execute()
            print(f"  Poistettu tuplakappale: {g.get('summary')}")
        else:
            nykyiset[mid] = g

    lisatty = paivitetty = poistettu = ennallaan = 0

    for mid, runko in halutut.items():
        vanha = nykyiset.get(mid)
        if vanha is None:
            palvelu.events().insert(calendarId=kalenteri_id, body=runko).execute()
            print(f"  + Lisätty:    {runko['summary']}  ({nayta_aika(runko)})")
            lisatty += 1
        elif vanha["extendedProperties"]["private"].get("sormenjalki") != \
                runko["extendedProperties"]["private"]["sormenjalki"]:
            palvelu.events().update(calendarId=kalenteri_id, eventId=vanha["id"], body=runko).execute()
            print(f"  ~ Päivitetty: {runko['summary']}  ({nayta_aika(runko)})")
            paivitetty += 1
        else:
            ennallaan += 1

    for mid, vanha in nykyiset.items():
        if mid not in halutut:
            palvelu.events().delete(calendarId=kalenteri_id, eventId=vanha["id"]).execute()
            print(f"  - Poistettu:  {vanha.get('summary')}")
            poistettu += 1

    print(f"Valmis! Lisätty {lisatty}, päivitetty {paivitetty}, "
          f"poistettu {poistettu}, ennallaan {ennallaan}.")


# ------------------------------------------------------------
# Pääohjelma
# ------------------------------------------------------------

def kokeile(url):
    """Näyttää, mitkä tapahtumat siirrettäisiin, koskematta Googleen."""
    nyt = dt.datetime.now(TZ)
    loppuraja = nyt + dt.timedelta(days=asetukset.PAIVIA_ETEENPAIN)
    tapahtumat = sorted(hae_myclub_tapahtumat(url), key=lambda t: aikaleimaksi(t["alku"]))
    print(f"myClubista löytyi {len(tapahtumat)} tapahtumaa.")
    pelit = hae_leijonat_pelit()
    print(f"Leijonien tulospalvelusta löytyi {len(pelit)} tulevaa peliä.\n")
    lisaa_tv_linkit(tapahtumat, pelit)
    for t in tapahtumat:
        if aikaleimaksi(t["loppu"]) <= nyt:
            continue  # menneitä ei näytetä
        merkki = "MUKAAN" if kuuluu_mukaan(t, nyt, loppuraja) else "pois  "
        if isinstance(t["alku"], dt.datetime):
            aika = aikaleimaksi(t["alku"]).strftime("%d.%m. klo %H:%M")
        else:
            aika = t["alku"].strftime("%d.%m. koko päivä")
        print(f"[{merkki}] {aika}  {muotoile_otsikko(t['nimi'])}   (alkuperäinen: {t['nimi']})")
        if t.get("tv") and merkki == "MUKAAN":
            print("           " + t["tv"].replace("\n", "\n           "))


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--kokeile":
        if len(sys.argv) >= 3:
            url = sys.argv[2]
        else:
            url = input("Liitä myClubin kalenterilinkki ja paina Enter: ")
        kokeile(url)
        return

    url = os.environ.get("MYCLUB_ICS_URL", "").strip()
    kalenteri_id = os.environ.get("GOOGLE_CALENDAR_ID", "").strip()  # poistetaan ylimääräiset välilyönnit
    if not url or not kalenteri_id:
        sys.exit("Virhe: MYCLUB_ICS_URL ja GOOGLE_CALENDAR_ID pitää olla asetettuina.")

    nyt = dt.datetime.now(TZ)
    loppuraja = nyt + dt.timedelta(days=asetukset.PAIVIA_ETEENPAIN)

    print("Haetaan tapahtumat myClubista...")
    tapahtumat = hae_myclub_tapahtumat(url)
    print(f"Löytyi {len(tapahtumat)} tapahtumaa. Synkronoidaan Google-kalenteriin...")
    if not tapahtumat:
        # Turvatoimi: jos myClub palauttaa tyhjää (esim. linkki rikki),
        # ei poisteta vahingossa kaikkea Google-kalenterista.
        sys.exit("Varoitus: myClubista ei tullut yhtään tapahtumaa, joten mitään ei muutettu.")

    pelit = hae_leijonat_pelit()
    print(f"Leijonien tulospalvelusta löytyi {len(pelit)} tulevaa peliä.")
    lisaa_tv_linkit(tapahtumat, pelit)

    palvelu = yhdista_googleen()
    synkronoi(palvelu, kalenteri_id, tapahtumat, nyt, loppuraja)


def nayta_virhe(viesti):
    """Tulostaa virheen. GitHubissa virhe näkyy myös ajon yhteenvedossa
    (Annotations), joten sen näkee ilman lokien avaamista."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        siivottu = viesti.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::error title=myClub-botti::{siivottu}")
    else:
        print(viesti)


def selita_google_virhe(virhe):
    koodi = virhe.resp.status
    if koodi == 404:
        return ("Google-kalenteria ei löytynyt (404). Joko GOOGLE_CALENDAR_ID on väärin, "
                "tai kalenteria ei ole jaettu robotille kalenterirobotti@...iam.gserviceaccount.com.")
    if koodi == 403:
        return ("Robotilla ei ole lupaa muokata kalenteria (403). Anna kalenterin jakoasetuksissa "
                "robotille oikeus 'Tee muutoksia tapahtumiin'.")
    if koodi == 400:
        return f"Google ei hyväksynyt pyyntöä (400). Tarkista GOOGLE_CALENDAR_ID. Tarkemmin: {virhe}"
    return f"Google-virhe {koodi}: {virhe}"


if __name__ == "__main__":
    from googleapiclient.errors import HttpError
    try:
        main()
    except SystemExit as lopetus:
        if isinstance(lopetus.code, str):
            nayta_virhe(lopetus.code)
            sys.exit(1)
        raise
    except HttpError as virhe:
        nayta_virhe(selita_google_virhe(virhe))
        sys.exit(1)
    except Exception as virhe:
        nayta_virhe(f"Odottamaton virhe: {type(virhe).__name__}: {virhe}")
        raise
