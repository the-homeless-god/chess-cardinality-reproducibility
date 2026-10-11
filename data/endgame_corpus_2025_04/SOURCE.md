# Lichess Broadcast April 2025: внешний эндшпильный корпус

Источник: [официальный архив Lichess Broadcast](https://database.lichess.org/broadcast/),
файл [lichess_db_broadcast_2025-04.pgn.zst](https://database.lichess.org/broadcast/lichess_db_broadcast_2025-04.pgn.zst).
Лицензия трансляций — CC BY-SA 4.0; атрибуция: Lichess и
первоначальные трансляции, URL которых приведены в positions.csv.
Официальный [список SHA-256](https://database.lichess.org/broadcast/sha256sums.txt)
и локальная проверка скачанного архива дали:

    6b6fd9e9e79a94e80d0f556fb323ad951922fdff1f42089fc18a348e65d79624

В репозитории лежат только выбранные FEN, контекст последнего хода,
URL партий и [манифест отбора](selection_manifest.json). Архив PGN
находился во временной папке и в репозиторий не копировался.
Выборка создана [скриптом](../../select_context_corpus.py) до запроса
эндшпильных исходов и до сравнения двух политик. Она содержит 250
позиций: по 50 с 3, 4, 5, 6 и 7 фигурами, максимум одна на партию,
без FEN из мартовского корпуса.
