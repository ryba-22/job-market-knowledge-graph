# Adding a job offer

1. Zachowaj URL i datę pobrania.
2. Zapisz analizę jako `data/jobs/YYYY-MM-DD-company-role.json`.
3. Oddziel literalne evidence od interpretacji.
4. Używaj istniejących kanonicznych nazw węzłów, jeśli znaczenie jest to samo.
5. Dodawaj nowy węzeł dopiero, gdy pojęcie wnosi nową odpowiedzialność, capability, proces albo technologię.
6. Uruchom:
   `python3 scripts/build_graph.py && python3 tests/test_build_graph.py`
7. W review odpowiedz: co ta oferta dodała do grafu, co tylko wzmocniła i jakie hipotezy rynkowe zmieniła.
