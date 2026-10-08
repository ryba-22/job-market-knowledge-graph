# Aplikuj v2 — uruchamianie i obserwowanie na maszynie Ryba

Zmieniamy wyłącznie przepływ Aplikuj.pl z kategorii `IT/Informatyka`. Pozostałe portale i historyczne kolejki pozostają oddzielne. Nie wznawiaj starego planu `scale-04`, który zawierał 40 634 rekordy wszystkich branż.

## Najpierw: wejście do repozytorium

```bash
cd ~/job-market-knowledge-graph-scale05
git log -1 --oneline
```

## 1. Przygotuj indeks i niezmienny plan (jednorazowo)

```bash
bash scripts/aplikuj_v2.sh prepare
```

Ta komenda odczytuje strony listy kategorii IT, nie pełne treści indywidualnych ofert. Odkrywa Aplikuj.pl **bez filtrowania tytułów**, zapisuje indeks w `.local-crawl/scale-04-it-v2/inventory` i plan w pliku `chunks.json`. Plan grupuje po 50 pozycji; wynik może się różnić od historycznych 509. Nie wykonuj `prepare` ponownie dla tej samej kolejki — zmiana listy ID między przebiegami zmieniłaby mapping chunk index → source IDs.

## 2. Uruchom pobieranie właściwych ogłoszeń (tylko po decyzji operatora)

```bash
bash scripts/aplikuj_v2.sh start
```

Crawler wystartuje w odłączonej sesji `tmux` `aplikuj-it-v2`, a logi będą w `.local-crawl/scale-04-it-v2/crawler.log`. Kontynuuje wcześniej rozpoczęty, **identyczny plan**, pomijając poprawnie ukończone paczki. Używa limitu 4 równoległych workerów dla Aplikuj.pl. Nie uruchamiaj drugiej kopii tego samego planu.

## 3. Śledzenie

```bash
bash scripts/aplikuj_v2.sh status
bash scripts/aplikuj_v2.sh watch
bash scripts/aplikuj_v2.sh logs
```

`status`: aktualny stan procesu (`RUNNING` / `STOPPED`) i zawartość `status.json`. `watch`: odświeżanie co 5 sekund. `logs`: strumień wyników zakończonych paczek i błędów. `Ctrl+C` wychodzi z `watch` lub `logs`, **nie przerywa crawlera**, ponieważ działa on w `tmux`.

Przykład samodzielnego podglądu:

```bash
watch -n 5 "jq '{updated_at,aplikuj:.sources.aplikuj,total:.total}' .local-crawl/scale-04-it-v2/status.json"
```

Interpretacja: `planned` = liczba unikalnych ID w nowym planie, `postings` = zarchiwizowane oferty (nie wszystkie muszą być technicznym IT), `source_gone` = niedostępne 404/410, `errors` = nieudane paczki/rekordy, `chunks_done` = paczki w pełni rozliczone, `pct` = udział rekordów rozliczonych przez **gotowe paczki** (nie postęp pojedynczego żądania). `assessment_counts` pokazuje `IT_CONFIRMED`, `NON_IT_CONFIRMED`, `REVIEW_REQUIRED`; wszystkie trzy są zachowane. Nawet 100% nie oznacza, że wszystkie oferty branży IT w Polsce są zebrane — tylko że ukończono jedną kolejkę źródłową.

## 4. Zatrzymanie i wznowienie

```bash
bash scripts/aplikuj_v2.sh stop
bash scripts/aplikuj_v2.sh status
bash scripts/aplikuj_v2.sh start
```

`stop` przekazuje `Ctrl+C` do procesu w `tmux`, bez kasowania plików archiwum. Ponowny `start` kontynuuje tę samą kolejkę; niezakończone paczki będą przetwarzane ponownie. Nie kasuj ręcznie `manifest.json` ani `chunks.json`.

## 5. Po zakończeniu: kontrola integralności

```bash
bash scripts/aplikuj_v2.sh verify
```

`PASS` oznacza, że każdy wykryty blok v2 ma zgodne archiwa korpusu, surowej obserwacji i klasyfikacji (identity, sha256, liczby). `NOT_RUN` to brak paczek. `FAIL` oznacza wymagającą naprawy niespójność.

**Przed uznaniem zadania za zakończone**: `status` nie może już wskazywać `RUNNING`; `errors` musi wynosić 0, `chunks_done == chunks_total`, `accounted == planned`, a `verify` musi być `PASS` przy dodatniej liczbie rekordów. Zakończenie sesji `tmux` bez tych warunków nie oznacza sukcesu.

## Bezpieczeństwo zakresu

- CLI opiera się na nowym `aplikuj_scope=it-category-v2`; stare plany v1 są odrzucane.
- Archiwum v1 nie jest nadpisywane. Historycznych 13 717 usuniętych rekordów z przeszłego pełnego sitemap crawl nie odzyskuje się automatycznie; nowe v2 dotyczy bieżącej kategorii IT.
- `prepare` nie uruchamia pobierania treści ofert, `status/watch/logs/verify` są tylko obserwacyjne, `start` jest świadomą operacją uruchomienia.
