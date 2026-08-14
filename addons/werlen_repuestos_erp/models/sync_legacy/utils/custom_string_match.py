import re
import unicodedata

from rapidfuzz import process


def normalize(text):
    if not text:
        return ""

    text = "".join(
        character
        for character in unicodedata.normalize("NFD", str(text))
        if unicodedata.category(character) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9 ]", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


PROVINCE_MAP = {
    "SALTA": "Salta",
    "BUENOS AIRES": "Buenos Aires",
    "BS AS": "Buenos Aires",
    "BSAS": "Buenos Aires",
    "BS AIRES": "Buenos Aires",
    "BUENOS AIRES PROVINCIA": "Buenos Aires",
    "PROVINCIA BUENOS AIRES": "Buenos Aires",
    "B AIRES": "Buenos Aires",
    "BUENOS AS": "Buenos Aires",
    "CIUDAD AUTONOMA DE BUENOS AIRES": "Ciudad Autónoma de Buenos Aires",
    "CABA": "Ciudad Autónoma de Buenos Aires",
    "CAPITAL FEDERAL": "Ciudad Autónoma de Buenos Aires",
    "CIUDAD DE BS AS": "Ciudad Autónoma de Buenos Aires",
    "CIUDAD DE BUENOS AIRES": "Ciudad Autónoma de Buenos Aires",
    "CAP FEDERAL": "Ciudad Autónoma de Buenos Aires",
    "SAN LUIS": "San Luis",
    "SL": "San Luis",
    "ENTRE RIOS": "Entre Ríos",
    "ENTRE RIO": "Entre Ríos",
    "E RIOS": "Entre Ríos",
    "E RIO": "Entre Ríos",
    "ER": "Entre Ríos",
    "PARANA": "Entre Ríos",
    "LA RIOJA": "La Rioja",
    "RIOJA": "La Rioja",
    "SANTIAGO DEL ESTERO": "Santiago del Estero",
    "SDE": "Santiago del Estero",
    "SANTIAGO ESTERO": "Santiago del Estero",
    "SGO DEL ESTERO": "Santiago del Estero",
    "CHACO": "Chaco",
    "CHA": "Chaco",
    "SAN JUAN": "San Juan",
    "SJ": "San Juan",
    "CATAMARCA": "Catamarca",
    "CATA": "Catamarca",
    "LA PAMPA": "La Pampa",
    "PAMPA": "La Pampa",
    "MENDOZA": "Mendoza",
    "MZA": "Mendoza",
    "MISIONES": "Misiones",
    "MISI": "Misiones",
    "MSN": "Misiones",
    "FORMOSA": "Formosa",
    "FRM": "Formosa",
    "NEUQUEN": "Neuquén",
    "NQN": "Neuquén",
    "NEUQUEN CAPITAL": "Neuquén",
    "RIO NEGRO": "Río Negro",
    "RN": "Río Negro",
    "SANTA FE": "Santa Fe",
    "STA FE": "Santa Fe",
    "S FE": "Santa Fe",
    "SF": "Santa Fe",
    "TUCUMAN": "Tucumán",
    "TUC": "Tucumán",
    "CHUBUT": "Chubut",
    "CHUB": "Chubut",
    "TIERRA DEL FUEGO": "Tierra del Fuego",
    "TDF": "Tierra del Fuego",
    "TIERRA FUEGO": "Tierra del Fuego",
    "CORRIENTES": "Corrientes",
    "CTES": "Corrientes",
    "CORR": "Corrientes",
    "CORDOBA": "Córdoba",
    "CBA": "Córdoba",
    "CDOBA": "Córdoba",
    "CORDO": "Córdoba",
    "JUJUY": "Jujuy",
    "JJY": "Jujuy",
    "SANTA CRUZ": "Santa Cruz",
    "STA CRUZ": "Santa Cruz",
    "SC": "Santa Cruz",
}


def match_province(raw):
    normalized = normalize(raw)
    if not normalized:
        return ""

    result = process.extractOne(normalized, list(PROVINCE_MAP), score_cutoff=70)
    if result:
        return PROVINCE_MAP[result[0]]
    return str(raw).strip()


def match_city(raw, existing_cities):
    raw = str(raw or "").strip()
    if not raw or not existing_cities:
        return raw

    normalized_cities = [normalize(city) for city in existing_cities]
    result = process.extractOne(normalize(raw), normalized_cities, score_cutoff=90)
    if result:
        return existing_cities[normalized_cities.index(result[0])]
    return raw
