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
import sys
from zoneinfo import ZoneInfo

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

    tapahtumat = []
    for osa in kalenteri.walk("VEVENT"):
        alku = osa.decoded("DTSTART")
        if "DTEND" in osa:
            loppu = osa.decoded("DTEND")
        elif "DURATION" in osa:
            loppu = alku + osa.decoded("DURATION")
        else:
            loppu = alku + dt.timedelta(hours=1)

        tapahtumat.append({
            "uid": str(osa.get("UID", "")),
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


def tee_google_tapahtuma(tapahtuma):
    """Muuttaa myClub-tapahtuman Google-kalenterin muotoon."""
    runko = {
        "summary": muotoile_otsikko(tapahtuma["nimi"]),
        "location": tapahtuma["paikka"],
        "description": tapahtuma["kuvaus"],
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
    print(f"myClubista löytyi {len(tapahtumat)} tapahtumaa.\n")
    for t in tapahtumat:
        if aikaleimaksi(t["loppu"]) <= nyt:
            continue  # menneitä ei näytetä
        merkki = "MUKAAN" if kuuluu_mukaan(t, nyt, loppuraja) else "pois  "
        if isinstance(t["alku"], dt.datetime):
            aika = aikaleimaksi(t["alku"]).strftime("%d.%m. klo %H:%M")
        else:
            aika = t["alku"].strftime("%d.%m. koko päivä")
        print(f"[{merkki}] {aika}  {muotoile_otsikko(t['nimi'])}   (alkuperäinen: {t['nimi']})")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--kokeile":
        if len(sys.argv) >= 3:
            url = sys.argv[2]
        else:
            url = input("Liitä myClubin kalenterilinkki ja paina Enter: ")
        kokeile(url)
        return

    url = os.environ.get("MYCLUB_ICS_URL")
    kalenteri_id = os.environ.get("GOOGLE_CALENDAR_ID")
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

    palvelu = yhdista_googleen()
    synkronoi(palvelu, kalenteri_id, tapahtumat, nyt, loppuraja)


if __name__ == "__main__":
    main()
