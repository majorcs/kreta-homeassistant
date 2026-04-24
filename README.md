# Kreta Home Assistant

> **Fontos:** ez egy **nem hivatalos** Home Assistant integráció. Nem áll kapcsolatban a Kreta rendszer eredeti fejlesztőivel vagy üzemeltetőivel.

## Mi ez?

A Kreta Home Assistant egy olyan egyedi integráció, amely a Kreta rendszer egyes tanulói adatait megjeleníti a Home Assistant felületén.

Az integráció célja, hogy a napi iskolai információk egyszerűbben jelenjenek meg otthoni automatizálásban és családi információs felületeken.

## Főbb funkciók

- órarend megjelenítése a Home Assistant naptárában
- bejelentett számonkérések megjelenítése az órarendi bejegyzések mellett, vagy külön naptári eseményként
- gépileg jól feldolgozható JSON szöveges szenzor az órarendi és vizsgaadatokhoz
- több tanuló kezelése külön integrációs példányokkal

## Telepítés

### HACS használatával

1. Nyisd meg a HACS felületet a Home Assistantban.
2. Add hozzá ezt a tárolót, ha egyedi tárolóként van szükség rá.
3. Telepítsd a **Kreta Home Assistant** integrációt.
4. Indítsd újra a Home Assistantot, ha erre a rendszer figyelmeztet.

### Kézi telepítéssel

1. Másold a projekt `custom_components/kreta` mappáját a saját Home Assistant rendszered `custom_components` könyvtárába.
2. Indítsd újra a Home Assistantot.

## Beállítás

1. Nyisd meg a **Beállítások / Eszközök és szolgáltatások** oldalt.
2. Válaszd az **Integráció hozzáadása** lehetőséget.
3. Keresd meg a **Kreta** integrációt.
4. Add meg a szükséges adatokat:
   - Kreta KLIK azonosító
   - felhasználói azonosító
   - jelszó
   - frissítési időköz
   - naptári időtartam hetekben

Ha több gyermekhez több Kreta-hozzáférésed van, minden tanulóhoz külön integrációs példány hozható létre.

## Használat

- Az órák és a számonkérések a Home Assistant naptárában jelennek meg.
- A JSON szöveges szenzor külső eszközökkel vagy automatizmusokkal is felhasználható.
- Az adatok a beállított frissítési időköz szerint frissülnek.

## Jogi megjegyzés

Ez a projekt közösségi, nem hivatalos megoldás. A Kreta név, a Kreta rendszer, valamint a kapcsolódó védjegyek és szolgáltatások a jogos tulajdonosaikhoz tartoznak. A projekt célja kizárólag a végfelhasználói integráció és az otthoni automatizálási felhasználás támogatása.
