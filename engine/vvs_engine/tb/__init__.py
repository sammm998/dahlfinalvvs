"""Teknisk beskrivning: läs en beskrivning utan ritningar och ta ut allt material den föreskriver.

En teknisk beskrivning enligt AMA är en tabell i fyra kolumner - KOD, TEXT, MÄNGD, ENHET - där AMA-koden står
till vänster (PRB.12 Golvbrunnar av rostfritt stål), posterna i fetstil i textkolumnen (B202B) med sin mängd
till höger (1 st), och under posten dess text, dess specifikation och det som hör till den ("Härtill:").

    reader  PDF -> poster med kod, mängd, fabrikat, typ, RSK-nummer, specifikation och kategori
    match   posterna mot materialboken och Dahls katalog: hittad, möjlig träff eller saknas
    mail    ett mejlutkast för det som inte hittades
    catalog Dahls produktkatalog som sökbart index
"""
from .reader import read_tech_spec, read_tech_spec_bytes  # noqa: F401
