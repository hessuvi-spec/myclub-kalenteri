# ------------------------------------------------------------
#  ASETUKSET – muokkaa tätä tiedostoa mielesi mukaan
# ------------------------------------------------------------
# Salaisia tietoja (myClub-linkki, Google-avain) EI kirjoiteta tänne,
# vaan ne annetaan GitHubin "Secrets"-kohdassa. Katso LUEMINUT.md.


# Kuinka monen päivän päähän tapahtumia siirretään.
PAIVIA_ETEENPAIN = 180


# Suodatus: otetaan mukaan vain tapahtumat, joiden nimessä on jokin
# näistä sanoista. Isoilla ja pienillä kirjaimilla ei ole väliä.
# Jos lista on tyhjä [], kaikki tapahtumat otetaan mukaan.
MUKAAN_JOS_NIMESSA = []
# Esimerkki:  MUKAAN_JOS_NIMESSA = ["harjoitus", "jäät", "ottelu", "peli"]


# Tapahtumat, joiden nimessä on jokin näistä sanoista, jätetään pois.
POIS_JOS_NIMESSA = ["punainen", "sininen"]
# Esimerkki:  POIS_JOS_NIMESSA = ["vanhempainpalaveri", "talkoot"]


# Otsikon alkuun lisättävä merkki tapahtuman tyypin mukaan.
# Vasemmalla hakusana (etsitään tapahtuman nimestä), oikealla lisättävä teksti.
# Ensimmäinen osuma voittaa.
OTSIKON_ALKU = {
    "ottelu": "🥅",
    "peli": "🥅",
    "turnaus": "🏆",
    "oheis": "🏃",
    "harjoitus": "🏒",
    "jäät": "🏒",
}
# Jos mikään hakusana ei osu, käytetään tätä (tyhjä "" = ei mitään).
OTSIKON_ALKU_MUUTEN = "📅"


# Poistetaanko otsikosta joukkueen nimi tms. turha teksti?
# Kirjoita tähän tekstit, jotka haluat poistaa otsikoista.
POISTA_OTSIKOSTA = []
# Esimerkki:  POISTA_OTSIKOSTA = ["U12 Kiekkoseura -", "(joukkue)"]


# Aikavyöhyke
AIKAVYOHYKE = "Europe/Helsinki"
