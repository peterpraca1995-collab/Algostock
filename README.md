# Investičná appka — technická analýza (paper trading)

Appka, ktorá každých 15 minút (počas obchodných hodín US trhu) stiahne
15-minútové sviečky pre sledované symboly, spočíta technické indikátory,
rozhodne o signáli a — na **paper (demo) účte** Alpaca — automaticky
otvorí/zatvorí pozíciu. Cieľ je čo najpresnejšie chytiť vnútrodenný smer,
nie držať pozíciu cez noc — appka preto pred zatvorením trhu každú
otvorenú pozíciu sama zatvorí, deň sa tak vždy vyhodnotí sám v sebe.
Bežia peniaze naničmo, nič reálne sa neobchoduje.

Beží ako **GitHub Actions cron job** — nezávisle od toho, či máš zapnutý
počítač. Dashboard je statická stránka (GitHub Pages), pozrieš si ju z
telefónu aj odkiaľkoľvek.

## Nasadenie na GitHub Actions (urob raz)

1. **Vytvor nové prázdne repo** na github.com (Settings ikonka vpravo hore →
   "+" → *New repository*). Nedávaj žiadny README/gitignore, chceme prázdne repo.
2. V termináli v priečinku `investicna-app`:
   ```bash
   git remote add origin https://github.com/<tvoj-github-účet>/<názov-repa>.git
   git branch -M main
   git push -u origin main
   ```
3. **Pridaj API kľúče ako GitHub Secrets** (repo → Settings → Secrets and
   variables → Actions → *New repository secret*):
   - `ALPACA_KEY_ID` = obsah `kluce/alpaca_paper_key_id.key`
   - `ALPACA_SECRET_KEY` = obsah `kluce/alpaca_paper_secret.key`
   
   Toto je zámerne krok, ktorý musíš urobiť ty sám v GitHub UI — kľúče sa
   nikdy neposielajú/neukladajú cez appku ani cez mňa.
4. **Zapni GitHub Pages** (repo → Settings → Pages → Source: *Deploy from a
   branch* → Branch: `main`, priečinok `/docs`). O pár minút bude dashboard na
   `https://<tvoj-účet>.github.io/<názov-repa>/`.
5. Hotovo. Workflow [`​.github/workflows/trading.yml`](.github/workflows/trading.yml)
   sa spúšťa automaticky každých 15 minút v obchodných hodinách (aj ručne cez
   záložku *Actions* → *Vyhodnotenie (paper trading)* → *Run workflow*, keby
   si chcel vidieť výsledok hneď a nečakať na najbližší 15-minútový krok).

Každý beh si po sebe zapíše výsledky (`data/trading.db`, `docs/data/status.json`)
späť do repa — tak si dashboard aj história vždy k dispozícii, nič sa nestráca.

## Lokálne spustenie (alternatíva)

Appku vieš spustiť aj priamo na svojom Macu — dvojklik na `Spustit-appku.command`,
alebo v termináli:

```bash
cd investicna-app
source .venv/bin/activate
python -m src.server
```

Otvorí sa `http://127.0.0.1:8765`. Appka ale musí fyzicky bežať (Mac zapnutý),
aby sa vyhodnotenia diali — preto je pre bežné používanie lepšia
GitHub Actions verzia vyššie.

## Sledované symboly a stratégia

Nastavenie: [`config/settings.json`](config/settings.json)

- **15 symbolov** — mega-cap tech (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA),
  polovodiče (AMD, AVGO), ďalšie likvidné mená naprieč sektormi (NFLX, PLTR,
  JPM, SOFI) a komodity cez ETF (GLD zlato, SLV striebro — Alpaca neobchoduje
  futures priamo). Vyberané zámerne naprieč sektormi/veľkosťou, nie len
  "mega-cap tech", nech je backtest/ladenie čo najmenej skreslené jedným typom trhu.
  (Rolls-Royce sa cez Alpaca obchodovať nedá — primárne kótovaná v Londýne,
  jej US OTC ADR RYCEY je na Alpaca označené ako netradovateľné.)
- 15-minútové sviečky (`15Min`) — kratší rámec než pôvodný `1Hour`, nech sa
  zachytí viac vnútrodenných pohybov. Indikátory sú počítané v počte sviečok,
  takže sa tým aj skrátila ich reálna pamäť (EMA9 ~2,25 h namiesto 9 h).
- **Pozície sa nedržia cez noc.** Posledných `flatten_before_close_minutes`
  (default 15) pred zatvorením trhu appka existujúcu pozíciu vždy zavrie
  a nové BUY už neotvára — účel je vnútrodenný smer, deň sa má vyhodnotiť
  sám v sebe.
- **Skórovací systém — 8 indikátorov hlasuje** (`src/strategy.py`), každý -1/0/+1:
  - `trend` — EMA9 vs EMA21 (smer)
  - `rsi` — RSI14 momentum, mimo extrémov (prekúpené/prepredané = bez hlasu)
  - `macd` — MACD histogram (smer momentu)
  - `cci` — CCI20, hlasuje len pri silnom breakoute (>+100 / <-100)
  - `fib` — cena sa odráža od Fibonacci retracement úrovne (23.6/38.2/50/61.8/78.6 %,
    počítané zo swing high/low za posledných 60 sviečok) v smere trendu
  - `bb` — Bollinger %B, cena sa odráža od dolného/horného pásma (volatilita/mean-reversion)
  - `stoch` — Stochastic %K/%D kríž z prepredanosti/prekúpenosti (iné časovanie než RSI)
  - `vwap` — cena nad/pod session VWAP (objemovo vážená cena, štandard pre intradenné obchodovanie)
  - Súčet hlasov = **skóre**. Vstup (BUY) pri skóre ≥ `signal_buy_threshold`
    (default +4 z max ±8), exit (SELL) pri skóre ≤ `signal_sell_threshold` (default -3,
    zámerne citlivejšie na exit než na vstup). Prahy sa dajú ladiť v `config/settings.json`.
  - **ADX14 ako filter sily trendu** — aj keď skóre prah splní, appka BUY neurobí, ak
    ADX < `adx_min_trend` (default 20): trh práve nemá skutočný trend (chop/sideways),
    signály sú tam nespoľahlivé. Neplatí pre exit — z pozície appka vždy vie odísť.
  - V dashboarde aj v logu je vidieť presný rozpis hlasov za každý indikátor —
    nikdy nie je to "čierna skrinka".
- Každá kúpa ide ako **bracket order** — stop-loss vo vzdialenosti `2×ATR14`
  pod vstupom a take-profit `3×ATR14` nad vstupom. Tieto sa strážia priamo na
  strane Alpaca (funguje aj keď appka práve nebeží), nie appkou samotnou.
- Alokácia na symbol: `allocation_per_symbol_usd` v settings.json (default $3000)

Toto je štartovacia, zámerne jednoduchá stratégia — dá sa a **oplatí sa ju
ladiť** až po pár týždňoch pozorovania, ako sa správa.

## Backtest a per-symbolové ladenie

```bash
python3 scripts/run_backtest.py                       # posledné 3 mesiace
python3 scripts/run_backtest.py 2026-07-01 2026-08-25  # vlastný rozsah
python3 scripts/optimize.py                            # per-symbol ladenie, posledný rok
```

`run_backtest.py` simuluje deň po dni presne to, čo appka robí naživo
(`src/backtest.py`), nad tou istou `strategy.decide()` logikou — žiadna
oddelená kópia pravidiel medzi backtestom a živým obchodovaním.

`optimize.py` rieši, že sledované tickery majú rôznu volatilitu a
jedny globálne prahy im nemusia sedieť rovnako. Pre každý symbol
vyskúša mriežku kombinácií (`signal_buy_threshold`, `signal_sell_threshold`,
`adx_min_trend`, ATR násobky stopu/cieľa) na prvých ~8 mesiacoch roka
a najlepšiu overí na posledných ~4 mesiacoch, ktoré pri hľadaní vôbec
nevidela (walk-forward) — override sa do `config/settings.json` (kľúč
`overrides`) zapíše len keď na tomto neviditeľnom úseku naozaj prekonal
default, nie len na dátach, kde sa hľadal. Bez toho by šlo o
prispôsobenie sa šumu, nie o skutočné zlepšenie.

**Aj tak s tým počítaj:** malý rozdiel medzi train a test výsledkom
(napr. TSLA) je dôveryhodný; veľký rozdiel (train omnoho lepší než test,
aj keď test ešte prekonal default) znamená, že aj vyladený nástroj môže
byť pre túto stratégiu jednoducho nespoľahlivý — vtedy má zmysel ho
sledovať ďalej, nie brať override ako hotovú vec.

## Ako appka funguje

```
src/alpaca_client.py    – REST volania na Alpaca (dáta + obchody)
src/indicators.py       – EMA, RSI, MACD, ATR, CCI, Fibonacci retracement (čistý Python)
src/strategy.py         – skórovacia rozhodovacia logika (8 indikátorov hlasuje)
src/engine.py           – jeden "tick": dáta → indikátory → skóre → obchod → log
src/backtest.py         – tá istá logika na historických sviečkach (bez Alpaca účtu)
src/scheduler.py        – lokálny variant plánovača (background vlákno) — pre beh na Macu
src/db.py               – SQLite log (data/trading.db) — história signálov aj equity krivka
src/export_status.py    – export data/trading.db → docs/data/status.json pre statický dashboard
src/server.py           – lokálny Flask dashboard + REST API (alternatíva k docs/)
scripts/run_tick.py     – vstupný bod pre GitHub Actions (jedno vyhodnotenie + export)
scripts/run_backtest.py – spustí backtest, viď vyššie
scripts/optimize.py     – per-symbolové walk-forward ladenie, viď vyššie
.github/workflows/      – 15-minútový cron job
docs/                    – statický dashboard pre GitHub Pages (HTML/JS/CSS, žiadne CDN závislosti)
web/                     – rovnaký dashboard pre lokálny Flask server
```

Dashboard ukazuje: stav účtu, aktuálne indikátory a skóre pre každý symbol,
otvorené pozície, equity krivku a log posledných rozhodnutí (aj tých, kde
appka nič neurobila — vidno presne *prečo*, vrátane rozpisu hlasov).

## API kľúče

- **Lokálne**: `../kluce/alpaca_paper_key_id.key` a `../kluce/alpaca_paper_secret.key`
  (mimo tohto priečinka, rovnaký vzor ako `entsoe.key`/`agsi.key`)
- **GitHub Actions**: repository secrets `ALPACA_KEY_ID` / `ALPACA_SECRET_KEY`
  (pozri postup nasadenia vyššie) — appka najprv skúsi tieto premenné
  prostredia, až potom lokálne súbory.

## Prechod na reálne peniaze — až po overení

`src/config.py` má `ALPACA_TRADING_BASE` nastavené na `paper-api.alpaca.markets`.
Prechod na live účet by znamenal:

1. Na Alpaca vygenerovať **live** API kľúče (samostatný, reálny účet s peniazmi)
2. Zmeniť `ALPACA_TRADING_BASE` na `https://api.alpaca.markets` a nahradiť kľúče
3. Toto je zámerne **manuálny krok, ktorý spravíš ty** — appka sama medzi
   paper a live neprepína, a odporúčam to spraviť až po dostatočne dlhom
   sledovaní výkonu na demo účte (equity krivka + log v dashboarde).

## Známe obmedzenia (MVP)

- Beží na GitHub Actions, takže nezávisí od zapnutého Macu — jediné riziko je,
  že GitHub pri `*/15` frekvencii vie beh občas o pár minút meškať/preskočiť
  pri väčšom zaťažení; appka to prežije, len sa vyhodnotí o čosi neskôr.
- Veľkosť pozície je vždy v celých kusoch akcií (žiadne zlomkové podiely).
- Dátový feed je Alpaca IEX (free) — mierne odlišný objem/ceny od hlavných búrz,
  bežné pre menšie účty.
- Jeden beh = max. jedna pozícia na symbol; appka nepridáva do pozície (pyramídenie).
