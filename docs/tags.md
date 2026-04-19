# Polymarket / Dome API tag reference

Sampled from `/polymarket/markets?status=closed&start_time=2023-01-01&end_time=2025-01-01`
(~5000 resolved markets, 50 pages of 100). Counts are market occurrences in that sample — a rough
signal of how populous a tag is, not an exhaustive universe. Unknown tags return empty results
rather than errors.

The `tags=` query parameter matches the label **case-insensitively** but **as an exact string** —
e.g. `tags=Silver` also matches markets carrying the lowercase tag `silver` (Nate Silver / 538
prediction markets), not just precious-metal markets. Inspect the resulting markets' titles
before trusting a tag's meaning. Multiple `tags=` parameters are combined with OR semantics.

## Climate & Weather

| Tag | Count |
|---|---:|
| `Weather` | 18 |

Not observed in the sample: `Climate`, `Hurricane`, `Hurricanes`

## Commodities

| Tag | Count |
|---|---:|
| `Commodities` | 9 |
| `Gold` | 9 |

Not observed in the sample: `Commodity Prices`, `Copper`, `Gas`, `Oil`, `Silver`

## Economics

| Tag | Count |
|---|---:|
| `Economy` | 109 |
| `Fed Rates` | 53 |
| `Economic Policy` | 28 |
| `Jerome Powell` | 25 |
| `Fed` | 11 |
| `Inflation` | 4 |

Not observed in the sample: `CPI`, `Economics`, `GDP`, `Interest Rates`, `Jobs`, `Recession`, `Unemployment`

## Financials

| Tag | Count |
|---|---:|
| `Crypto Prices` | 247 |
| `Bitcoin` | 108 |
| `Ethereum` | 55 |
| `finance` | 51 |
| `IPOs` | 1 |

Not observed in the sample: `Earnings`, `Finance`, `IPO`, `Stocks`

## Business/Companies

| Tag | Count |
|---|---:|
| `Business` | 206 |

Not observed in the sample: `Companies`

## Politics

| Tag | Count |
|---|---:|
| `Politics` | 1333 |
| `Trump` | 777 |
| `Mentions` | 443 |
| `Trump Presidency` | 410 |
| `US Election` | 171 |
| `Global Elections` | 149 |
| `Geopolitics` | 72 |
| `Biden` | 56 |
| `Gov Shutdown` | 41 |
| `Economic Policy` | 28 |
| `us government` | 24 |

## Elections

| Tag | Count |
|---|---:|
| `US Election` | 171 |
| `Global Elections` | 149 |
| `German Election` | 48 |

Not observed in the sample: `2024 Election`, `Elections`, `Presidential Election`

## Entertainment

| Tag | Count |
|---|---:|
| `Culture` | 553 |
| `Awards` | 158 |
| `Movies` | 93 |
| `Music` | 58 |
| `Grammys` | 24 |

Not observed in the sample: `Emmys`, `Entertainment`, `Oscars`, `Pop Culture`, `TV`

## Science & Tech

| Tag | Count |
|---|---:|
| `Tech` | 79 |
| `Science` | 57 |
| `AI` | 54 |
| `DeepSeek` | 38 |
| `Grok` | 19 |
| `SpaceX` | 13 |

Not observed in the sample: `NASA`, `Space`

## Sports

| Tag | Count |
|---|---:|
| `Sports` | 2609 |
| `Games` | 2013 |
| `NBA` | 598 |
| `Soccer` | 457 |
| `NFL` | 415 |
| `EPL` | 333 |
| `CFB` | 330 |
| `Premier League` | 303 |
| `NHL` | 224 |
| `Esports` | 105 |
| `Chess` | 88 |
| `Boxing` | 55 |
| `CFP` | 51 |
| `UFC` | 48 |
| `video games` | 32 |
| `Tennis` | 15 |
| `MLB` | 14 |
| `Golf` | 3 |

Not observed in the sample: `Cricket`

## Crypto

| Tag | Count |
|---|---:|
| `Crypto` | 333 |
| `Crypto Prices` | 247 |
| `Bitcoin` | 108 |
| `Ethereum` | 55 |
| `Solana` | 34 |
| `Airdrops` | 23 |

## Other popular

| Tag | Count |
|---|---:|
| `USA Election` | 390 |
| `Cabinet` | 265 |
| `futures` | 207 |
| `Twitter` | 168 |
| `Champions League` | 162 |
| `Europa League` | 153 |
| `Tweet Markets` | 152 |
| `2025 Predictions` | 116 |
| `Elon Musk` | 116 |
| `U.S. Politics` | 95 |
| `World` | 90 |
| `NCAA` | 87 |
| `football` | 77 |
| `Tournaments` | 67 |
| `World Elections` | 65 |
| `Kamala` | 65 |
| `Spreads` | 61 |
| `UEFA Nations League` | 60 |
| `Senate` | 56 |
| `Memecoins` | 56 |
| `Today's Sports` | 55 |
| `Breaking News` | 50 |
| `totals` | 49 |
| `Pete Hegseth` | 48 |
| `Margin of Victory` | 48 |
| `playoffs` | 45 |
| `Middle East` | 43 |
| `Trump 100 Days` | 42 |
| `Bowl Games` | 42 |
| `Inauguration` | 41 |
| `interview` | 41 |
| `House Races` | 38 |
| `f1` | 37 |
| `FIDE` | 37 |
| `Formula 1` | 37 |
| `Popular Vote` | 37 |
| `Luigi Mangione` | 36 |
| `NBA Cup` | 35 |
| `Brian Thompson` | 33 |
| `Basketball` | 33 |
| `internet` | 33 |
| `fights` | 32 |
| `First 100 days` | 31 |
| `Tulsi Gabbard` | 30 |
| `B1G` | 29 |
| `sec` | 29 |
| `House Poker Night` | 28 |
| `RFK Jr.` | 27 |
| `Europe` | 26 |
| `Congress` | 26 |
| `Kash Patel` | 26 |
| `Campaign Promises` | 26 |
| `box office` | 26 |
| `DOGE` | 26 |
| `Rogan` | 25 |
| `Poland` | 25 |
| `Vance` | 25 |
| `Week 10` | 25 |
| `JD` | 25 |
| `GRAMMY` | 24 |
| `nyc` | 24 |
| `Gukesh Dommaraju` | 24 |
| `Hit Price` | 24 |
| `Fight Night` | 24 |
| `Yearly` | 24 |
| `Ding Liren` | 24 |
| `Golden Globes` | 24 |
| `turnout` | 24 |
| `Israel` | 24 |
| `Post Election` | 23 |
| `Over/Under` | 22 |
| `NFL Draft` | 22 |
| `Magnus` | 22 |
| `MAGA` | 22 |
| `Creators` | 21 |
| `tucker carlson` | 21 |
| `Paul vs Tyson` | 21 |
| `house` | 20 |
| `Romania` | 20 |
| `New Mexico` | 20 |
| `interviews` | 20 |
| `manchester united` | 20 |
| `Week 15` | 20 |
| `Maps` | 20 |
| `Foreign Policy` | 19 |
| `Celebrities` | 19 |
| `oleksandr usyk` | 19 |
| `Paul vs. Tyson` | 19 |
| `Liverpool` | 19 |
| `arsenal` | 19 |
| `Tottenham` | 19 |
| `Usyk vs. Fury` | 19 |
| `tyson fury` | 19 |
| `France` | 19 |
| `World Chess Championship` | 18 |
| `props` | 18 |
| `Syria` | 18 |
| `Darts` | 18 |
| `fbi` | 18 |
| `Week 17` | 18 |
| `OpenAI` | 18 |
| `Polling` | 18 |
| `climate` | 18 |
| `Canada` | 17 |
| `Carabao Cup` | 17 |
| `UnitedHealthcare` | 17 |
| `Brazil` | 17 |
| `Big 12` | 17 |
| `South Korea` | 16 |
| `German Politics` | 16 |
| `Ann Selzer` | 16 |
| `exchange` | 16 |
| `XRP` | 16 |
| `Des Moines Register` | 16 |
| `DMR` | 16 |
| `Macro Election 2` | 16 |
| `New York` | 16 |
| `Usyk vs. Fury 2` | 16 |
| `Mystery Drones` | 16 |
| `Alexandria Ocasio-Cortez` | 15 |
| `Thanksgiving Football` | 15 |
| `Speaker` | 15 |
| `Ukraine` | 15 |
| `Valve` | 15 |
| `Big Tech` | 15 |
| `Houston` | 15 |
| `Speaker Election` | 15 |
| `georgia` | 15 |
| `Steam` | 15 |
| `cs2` | 14 |
| `bls` | 14 |
| `Global Temp` | 14 |
| `eth` | 14 |
| `England` | 14 |
| `Under` | 14 |
| `Week 9` | 14 |
| `ACC` | 14 |
| `Over` | 14 |
| `Dogecoin` | 14 |
| `jpow` | 14 |
| `Ripple` | 14 |
| `Sam Bankman` | 14 |
| `Week 16` | 13 |
| `New York City` | 13 |
| `Mayoral` | 13 |
| `NY` | 13 |
| `New Jersey Drones` | 13 |
| `NYC Mayor` | 13 |

## All observed tags with count ≥ 5

Excludes tags already listed above.

| Tag | Count |
|---|---:|
| `Miami` | 13 |
| `Colby Covington` | 13 |
| `Joaquin Buckley` | 13 |
| `Jake Paul` | 13 |
| `Mike Tyson` | 13 |
| `conggress` | 13 |
| `llm` | 12 |
| `Trudeau out` | 12 |
| `Penn State` | 12 |
| `Turkey` | 12 |
| `Sides` | 12 |
| `mma` | 12 |
| `barcelona` | 12 |
| `atletico madrid` | 12 |
| `bayern munich` | 12 |
| `rb leipzig` | 12 |
| `warriors` | 12 |
| `DPOY` | 12 |
| `international politics` | 12 |
| `attorney general` | 12 |
| `CONMEBOL` | 12 |
| `PAC12AFTERDARK` | 12 |
| `ron desantis` | 12 |
| `cabinet for trump` | 12 |
| `Secretary of Treasury` | 12 |
| `Overs` | 12 |
| `Unders` | 12 |
| `fox` | 12 |
| `deficit` | 11 |
| `russia` | 11 |
| `Immigration` | 11 |
| `Manchester City` | 11 |
| `Joe Burrow` | 11 |
| `Macro Jobs` | 11 |
| `baseball` | 11 |
| `Week 14` | 11 |
| `Cam Ward` | 11 |
| `Robinhood` | 11 |
| `Trump Week 1` | 11 |
| `running` | 11 |
| `marathon` | 11 |
| `ohio state` | 10 |
| `Pandemics` | 10 |
| `Taylor Swift` | 10 |
| `stock` | 10 |
| `India` | 10 |
| `Champions Chess Tour` | 10 |
| `spain` | 10 |
| `Southampton` | 10 |
| `newcastle` | 10 |
| `Brentford` | 10 |
| `Crystal Palace` | 10 |
| `Buckets` | 10 |
| `Butler` | 10 |
| `Jimmy` | 10 |
| `mavericks` | 10 |
| `Aston Villa` | 10 |
| `Comeback Player` | 10 |
| `damar` | 10 |
| `Roger Goodell` | 10 |
| `Damar Hamlin` | 10 |
| `art` | 10 |
| `ireland` | 10 |
| `PAC12` | 10 |
| `ATP Finals` | 10 |
| `Irish` | 10 |
| `clover` | 10 |
| `Taoiseach` | 10 |
| `metals` | 9 |
| `South Carolina` | 9 |
| `Iowa` | 9 |
| `Executive Actions` | 9 |
| `WNBA` | 9 |
| `Clemson` | 9 |
| `Macro Fed` | 9 |
| `Hailey Welch` | 9 |
| `Anderlecht` | 9 |
| `Slavia Praha` | 9 |
| `real sociedad` | 9 |
| `Dynamo Kyiv` | 9 |
| `Frankfurt` | 9 |
| `Lyon` | 9 |
| `Maccabi TLV` | 9 |
| `RFS` | 9 |
| `Bodo Glimt` | 9 |
| `IF Elfsborg` | 9 |
| `lazio` | 9 |
| `Ajax` | 9 |
| `Viktoria Plzen` | 9 |
| `Hoffenheim` | 9 |
| `FCSB` | 9 |
| `PAOK` | 9 |
| `Ferencvaros` | 9 |
| `greece` | 9 |
| `Twente` | 9 |
| `Braga` | 9 |
| `Ludogorets` | 9 |
| `AZ Alkmaar` | 9 |
| `Galatasaray` | 9 |
| `employment` | 9 |
| `RFK` | 9 |
| `Fenerbahce` | 9 |
| `Athletic Bilbao` | 9 |
| `Bologna` | 9 |
| `Benfica` | 9 |
| `Monaco` | 9 |
| `Young Boys` | 9 |
| `Stuttgart` | 9 |
| `Borussia Dortmund` | 9 |
| `Feyenoord` | 9 |
| `Sparta Praha` | 9 |
| `Juventus` | 9 |
| `Sturm Graz` | 9 |
| `Slovan Bratislava` | 9 |
| `AC Milan` | 9 |
| `Red Star Belgrade` | 9 |
| `Club Brugge` | 9 |
| `Sporting CP` | 9 |
| `Shakhtar Donetsk` | 9 |
| `Paris Saint-Germain` | 9 |
| `RB Salzburg` | 9 |
| `Stade Brestois` | 9 |
| `psv` | 9 |
| `inter milan` | 9 |
| `Bayer Leverkusen` | 9 |
| `real madrid` | 9 |
| `Atalanta` | 9 |
| `girona` | 9 |
| `Celtic` | 9 |
| `Dinamo Zagreb` | 9 |
| `healthcare` | 9 |
| `Abu Dhabi` | 9 |
| `racing` | 9 |
| `motorsports` | 9 |
| `qatar` | 9 |
| `iceland` | 9 |
| `San Diego State` | 9 |
| `food` | 9 |
| `drug` | 9 |
| `races` | 9 |
| `electoral` | 9 |
| `texas` | 8 |
| `trudeau` | 8 |
| `MicroStrategy` | 8 |
| `Bird Flu` | 8 |
| `washington` | 8 |
| `michigan` | 8 |
| `Lions` | 8 |
| `Missouri` | 8 |
| `Iran` | 8 |
| `rams` | 8 |
| `Antonio Brown` | 8 |
| `packers` | 8 |
| `Matchday 17` | 8 |
| `Goals` | 8 |
| `Hunter` | 8 |
| `Macro Unemployment` | 8 |
| `Macro Inflation` | 8 |
| `sol` | 8 |
| `democrat` | 8 |
| `exchanges` | 8 |
| `Kennedy` | 8 |
| `ATP` | 8 |
| `elector` | 8 |
| `Venezuela` | 7 |
| `global warming` | 7 |
| `ATH` | 7 |
| `Mark Carney` | 7 |
| `poilievre` | 7 |
| `broncos` | 7 |
| `chargers` | 7 |
| `Army` | 7 |
| `arkansas` | 7 |
| `Lonzo Ball` | 7 |
| `opensea` | 7 |
| `scorigami` | 7 |
| `pudgy penguins` | 7 |
| `$PENGU` | 7 |
| `belarus` | 7 |
| `pardon` | 7 |
| `zerohedge` | 7 |
| `Diddy` | 7 |
| `Roaring Kitty` | 7 |
| `poty` | 7 |
| `magazine` | 7 |
| `porn` | 7 |
| `shooting` | 7 |
| `Yoon Suk yeol` | 7 |
| `eu` | 7 |
| `usa` | 7 |
| `Jamaica` | 7 |
| `Florida` | 7 |
| `HHS` | 7 |
| `Dewine` | 7 |
| `Health and Human Services` | 7 |
| `Election Night` | 7 |
| `green` | 7 |
| `Ole Miss` | 6 |
| `College Football Playoff` | 6 |
| `Oregon` | 6 |
| `Declassification` | 6 |
| `Other` | 6 |
| `Boise State` | 6 |
| `Louisville` | 6 |
| `Federal` | 6 |
| `49ers` | 6 |
| `bengals` | 6 |
| `english` | 6 |
| `Michael Saylor` | 6 |
| `texans` | 6 |
| `Mackenzie Dern` | 6 |
| `Amanda Ribas` | 6 |
| `thunder` | 6 |
| `TNF` | 6 |
| `Jim Bianco` | 6 |
| `Jay-Z` | 6 |
| `Rangers` | 6 |
| `Eintracht` | 6 |
| `Besiktas` | 6 |
| `FC Midtjylland` | 6 |
| `porto` | 6 |
| `FK Qarabag` | 6 |
| `Olympiacos` | 6 |
| `AS Roma` | 6 |
| `payroll` | 6 |
| `nonfarm` | 6 |
| `farm` | 6 |
| `jobs` | 6 |
| `UHC` | 6 |
| `LOSC Lille` | 6 |
| `Assad` | 6 |
| `btc` | 6 |
| `GameStop` | 6 |
| `Daniel Penny` | 6 |
| `ding` | 6 |
| `Nice` | 6 |
| `ravens` | 6 |
| `Yan vs. Figueiredo` | 6 |
| `croatia` | 6 |
| `Serbia` | 6 |
| `Denmark` | 6 |
| `switzerland` | 6 |
| `scotland` | 6 |
| `italy` | 6 |
| `belgium` | 6 |
| `finland` | 6 |
| `Mountain West` | 6 |
| `UCLA` | 6 |
| `Pitt` | 6 |
| `arizona` | 6 |
| `moreno` | 6 |
| `Albazi` | 6 |
| `libertarian` | 6 |
| `Election Parlays` | 6 |
| `Duke` | 5 |
| `Featured` | 5 |
| `H5N1` | 5 |
| `LSU` | 5 |
| `Canadian Election` | 5 |
| `Macro Election 1` | 5 |
| `colorado` | 5 |
| `BYU` | 5 |
| `NC State` | 5 |
| `Texas A&M` | 5 |
| `Georgia Tech` | 5 |
| `H1b` | 5 |
| `MSTR` | 5 |
| `Open Source Intel` | 5 |
| `Indiana` | 5 |
| `SMU` | 5 |
| `stocks` | 5 |
| `UNLV` | 5 |
| `Rumors` | 5 |
| `bucks` | 5 |
| `bears` | 5 |
| `Hawk Tuah` | 5 |
| `Rotten Tomatoes` | 5 |
| `browns` | 5 |
| `cowboys` | 5 |
| `dolphins` | 5 |
| `Pantoja` | 5 |
| `Asakura` | 5 |
| `310` | 5 |
| `youtbe` | 5 |
| `auction` | 5 |
| `Germany` | 5 |
| `tennessee` | 5 |
| `Housing and Urban Development` | 5 |
| `309` | 5 |
| `Jones` | 5 |
| `Miocic` | 5 |
| `Stipe` | 5 |
| `Jon` | 5 |
| `ECB` | 5 |
| `interest rates` | 5 |
| `Swing States` | 5 |
| `mov` | 5 |
