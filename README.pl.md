# pullrequest-sandbox

Narzędzie testuje pull request tak, jak trafi on do repozytorium: scalony z najnowszym `main`, w jednorazowym
kontenerze Docker bez sieci, który nie zmienia żadnego pliku na komputerze.

[![Licencja: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Zależności: biblioteka standardowa](https://img.shields.io/badge/dependencies-standard%20library-brightgreen)](merge-sweep/sweep.py)
[![Kontener: bez sieci](https://img.shields.io/badge/container-network%20none-lightgrey)](bin/sandbox-run)

[English](README.md) | [Narzędzia](#narzędzia) | [Wyniki](#wyniki) | [Szybki start](#szybki-start) |
[Jak to działa](#jak-to-działa) | [Granice](#granice)

Narzędzie powstało przy review repozytorium [ItsNotRexed/Leonida](https://github.com/ItsNotRexed/Leonida), które
miało 4425 otwartych pull requestów `[pomiar: API GitHuba, 2026-11-23, 21:58 CET]`. Opis przypadku:
[Testowanie otwartych pull requestów scalonych z `main`](https://github.com/maciejszulia/maciejszulia/blob/main/case-studies/leonida-merge-sweep.md)
(po angielsku). Grafy scaleń: [README po angielsku, sekcja Graphs](README.md#graphs).

## Narzędzia

| Narzędzie | Pytanie, na które odpowiada |
| --- | --- |
| [`bin/sandbox-run`](bin/sandbox-run) | Jak uruchomić kod z cudzego pull requestu bez sieci i bez dostępu do moich plików? |
| [`merge-sweep/sweep.py`](merge-sweep/sweep.py) | Które otwarte pull requesty psują test dopiero po scaleniu z `main`? |
| [`merge-sweep/merge-check`](merge-sweep/merge-check) | Jaki jest wynik 1 pliku testów na `main`, po scaleniu i na samym head? |
| [`merge-sweep/merge-bisect`](merge-sweep/merge-bisect) | Do którego commita na `main` pull request MUSI się dostosować? |
| [`merge-sweep/train.py`](merge-sweep/train.py) | Które pull requesty mogą trafić na `main` razem, w 1 push, bez zepsutego testu? |
| [`tests/check_sandbox.sh`](tests/check_sandbox.sh) | Czy sandbox działa: brak sieci, źródło bez zmian, self-checki bisekcji i pociągu scaleń? |

## Wyniki

Repozytorium ItsNotRexed/Leonida, 2026-11-23, laptop ThinkPad T470p (i7-7700HQ, 32 GB RAM, Docker 29.10.0). Każda
liczba z commitem i godziną: [results/2026-11-23-leonida.md](results/2026-11-23-leonida.md).

| Co | Liczba |
| --- | --- |
| otwarte pull requesty sprawdzone przez `sweep.py` (`main` przy `dde82f27`, 3 procesy, 86 min) | 1667 |
| w tym konflikt scalenia z `main` | 304 |
| pliki testów, które padają po scaleniu, a przechodzą na `main` albo są nowe | 37 w 36 pull requestach |
| nadal padają tylko po scaleniu z `main` przy `6312c057` | 15 |
| w tym `merge-bisect` wskazał dokładny commit na `main` | 14 |
| `train.py` na 5 pull requestach: odrzucone, scalone w 1 tip, czas | 1, 4, 94 s |

## Szybki start

Wymagania: Linux, Docker, git w wersji co najmniej 2.38 oraz GitHub CLI (`gh`) do przeglądu wszystkich pull requestów.

```sh
git clone https://github.com/maciejszulia/pullrequest-sandbox.git && cd pullrequest-sandbox
docker build -t pullrequest-sandbox:py312 image
tests/check_sandbox.sh
bin/sandbox-run ~/lab/<repo> 'python -I tests/test_something.py'
```

Komendy przeglądu pull requestów 1 repozytorium podaje [README.md, sekcja Quick start](README.md#quick-start).

## Jak to działa

1. `bin/sandbox-run` montuje katalog tylko do odczytu, kopiuje go do tmpfs i uruchamia komendę z opcjami
   `--network none`, `--cap-drop ALL`, `no-new-privileges`, z użytkownikiem bez roota i z limitami pamięci, CPU
   oraz procesów.
2. `sweep.py` scala head każdego pull requestu z 1 migawką `main` przez `git merge-tree --write-tree` (bez
   katalogu roboczego) i uruchamia w kontenerze pliki testów, które pull request zmienia.
3. `merge-bisect` dzieli na pół historię first-parent `main` między merge base a migawką. Każdy krok scala head
   z 1 commitem `main` i uruchamia test.
4. `train.py` scala listę pull requestów lokalnie, uruchamia ich testy raz na tipie, odrzuca pull request, który
   zepsuł test, i buduje pociąg od nowa, co najwyżej 3 razy. Narzędzie niczego nie wysyła: 1 push tipu scala cały
   pociąg.

## Granice

- Kontener dzieli jądro z komputerem. Kontener odcina kod od sieci i od plików komputera, ale nie chroni przed
  kodem, który atakuje Dockera albo jądro.
- Reguła wyboru testów w [`merge-sweep/run_pr.sh`](merge-sweep/run_pr.sh) pochodzi z CI repozytorium
  ItsNotRexed/Leonida. Inne repozytorium MUSI zmienić ten blok.
- Przegląd obejmuje tylko pull requesty, które zmieniają pliki `.py` i `.md` oraz dotykają katalogu `tests/`.

## Licencja i autor

MIT. Maciej Szulia.
