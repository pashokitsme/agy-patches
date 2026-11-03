# agy-patches

Локальные бинарные патчи для Antigravity на macOS arm64:

- `cli/patch.py` — `agy` 1.4.12;
- `gui/patch.py` — `language_server` из Antigravity 2.28.2.

Патчи убирают локальный отказ вида `this account is ineligible ... not currently available in your location`. OAuth, токены, выбор модели и сетевые запросы не подменяются. Исходные бинарники и учётные данные в репозиторий не входят.

## Один вызов

```bash
./patch
```

Исполняемый файл показывает состояние установленных CLI и GUI и предлагает пропатчить CLI, GUI или оба сразу. Enter выбирает всё доступное. Для оригинальных бинарников автоматически создаются резервные копии в `~/.agy-patches/backups/`.

При выборе GUI скрипт предлагает завершить Antigravity, ждёт выхода, применяет патч, выполняет ad-hoc подпись и проверку `codesign`, затем предлагает снова запустить приложение. CLI подписывается и проверяется так же автоматически.

Только показать состояние без изменений:

```bash
./patch --check
```

## Как устроена проверка

После входа клиент получает результат авторизации и сведения об аккаунте. Даже при действительном OAuth-токене локальный код превращает ответ с неподходящим tier в `AuthResult` без `hasValidAuth`. CLI затем отказывается отправлять сообщение, а GUI показывает экран `ineligible`.

В использованных версиях отказ принимается на клиенте. После изменения одной ARM64-инструкции выполнение продолжается по обычному пути, включая `OnboardUser`, `GetUserStatus` и запросы генерации. Серверный ответ `LoadCodeAssistResponse` не изменяется.

CLI и GUI собраны из разного кода: функция `handleAuthResult` из `agy` отсутствует в GUI `language_server`. Поэтому это два независимых патча, а не одно смещение для обоих бинарников.

## CLI: agy 1.4.12

Цель по умолчанию: `~/.local/bin/agy`.

В `backend.(*ServerBackend).handleAuthResult.func1` условный переход ведёт в создание сохранённой ошибки ineligible. Патч заменяет его на безусловный переход к продолжению обработки результата:

| | Значение |
|---|---|
| VA | `0x10277ee6c` |
| File offset | `0x277ee6c` |
| До | `tbnz w2, #0, 0x10277eff4` |
| После | `b 0x10277eff4` |
| Байты | `420c0037` → `62000014` |
| SHA-256 оригинала | `34423fc9b0af3841e7646aa72a2d40ffeab8218b22d1cb99eac7355f9eba31e3` |
| SHA-256 patched до подписи | `bd0f26018c0eb608e00c83f42bcce8ed6c999829bdc24384bf914adb821c92ed` |

Предшествующая проверка `cbnz x1` сохраняется: настоящие ошибки OAuth не игнорируются.

### Ручная установка CLI

```bash
uv run --no-project python cli/patch.py --check
uv run --no-project python cli/patch.py
codesign --force --sign - ~/.local/bin/agy
agy --model gemini-4-argon-medium -p 'Ответь ровно: OK.'
```

Проверено: команда возвращает `OK`; отдельный запрос к `gemini-4-argon-medium` возвращает `Привет от Gemini 4 Argon.` В логе виден настоящий вызов `https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse`.

## GUI: Antigravity 2.28.2

Цель по умолчанию: `/Applications/Antigravity.app/Contents/Resources/bin/language_server`. `app.asar` и JavaScript интерфейса не изменяются.

`authclient.ValidateAndOnboardAccount` получает `LoadCodeAssistResponse`, ищет `free-tier` в `AllowedTiers` и обходит `IneligibleTiers`. Для непустого `IneligibleTier.ReasonMessage` условный переход ведёт в построение отказа с текстом для UI. Патч пропускает именно этот переход:

| | Значение |
|---|---|
| VA | `0x10237aa30` |
| File offset | `0x237aa30` |
| До | `cbnz x0, 0x10237ab14` |
| После | `b 0x10237aa34` |
| Байты | `200700b5` → `01000014` |
| SHA-256 оригинала | `8b660ea42c9e24b7a6be339bfa573d25b19d0770dba6e5185c205f2ad1da26d6` |
| SHA-256 patched до подписи | `bf3569b5b83310bb7a64dceed17c6bbd5cbef916ad81a0fdd4042c7afc2e248d` |

Здесь `x0` — длина строки, возвращённой `IneligibleTier.GetReasonMessage`. Ошибки `fetchLoadCodeAssistResponse`, `OnboardUser` и `GetUserStatus` обрабатываются другими ветками и продолжают возвращаться.

### Ручная установка GUI

Завершите Antigravity и сохраните копию оригинального `language_server` отдельно от репозитория. Затем:

```bash
uv run --no-project python gui/patch.py --check
uv run --no-project python gui/patch.py
codesign --force --sign - --preserve-metadata=entitlements /Applications/Antigravity.app/Contents/Resources/bin/language_server
codesign --force --deep --sign - --preserve-metadata=entitlements /Applications/Antigravity.app
codesign --verify --deep --strict --verbose=2 /Applications/Antigravity.app
open -a Antigravity
```

Проверка на копии без изменения установленного приложения:

```bash
uv run --no-project python gui/patch.py --target /полный/путь/к/копии/language_server
```

## Поведение скриптов

Низкоуровневые `cli/patch.py` и `gui/patch.py` используют только стандартную библиотеку Python и запускаются через `uv`:

1. Читают байты по заданному file offset.
2. Для оригинала сверяют полный SHA-256 с поддерживаемой версией.
3. Ничего не меняют при неизвестном хеше или неожиданных байтах.
4. Повторный запуск на patched-бинарнике ничего не перезаписывает; `--check` только сообщает состояние.
5. Создают новый файл в каталоге цели, проверяют исходные байты ещё раз и атомарно заменяют цель через `os.replace`.

Новый файл важен для подписанного Mach-O: macOS кэширует подпись по vnode, поэтому изменение существующего файла на месте может привести к `Code Signature Invalid` при следующем запуске.

## Подпись GUI

Изменение `language_server` делает исходную подпись Google недействительной. Все вложенные компоненты приложения подписываются заново локальной ad-hoc подписью, entitlements сохраняются.

Hardened runtime не сохраняется: на проверенной macOS 15 он отклонял загрузку Electron Framework с ошибкой `mapping process and mapped file (non-platform) have different Team IDs` даже после перевода всех компонентов на ad-hoc. `--deep` нужен, чтобы основной процесс и фреймворки имели согласованную подпись. SIP и системные настройки безопасности не изменяются. Разрешения, привязанные macOS к подписи приложения, могут быть запрошены повторно.

## Проверка GUI

На Antigravity 2.28.2 через REA выполнен полный сценарий:

1. Экран `ineligible` исчез, открылся основной интерфейс.
2. Выбрана `Gemini 4 Argon Medium`.
3. В поле ввода отправлен запрос `Reply with exactly GUI_ARGON_OK and do not use tools.`
4. В `Agent response` получен `GUI_ARGON_OK`.

REA Evidence: `ev_d228ebef97ada2eb5aebbd0aeec5f751b3de33fb4013dd4c254517a14c99e671`.

## Обновления и откат

`agy update` и обновление Antigravity перезаписывают соответствующий патч. После обновления снова запустите `./patch`. Если SHA-256 новой версии не совпадает с поддерживаемым, скрипт откажется её изменять: сначала нужно заново найти ветку проверки.

Для отката завершите приложение, восстановите оригинальный бинарник из `~/.agy-patches/backups/` новым файлом и повторите подписание. Это восстанавливает код, но не подпись Google: для полного восстановления исходных подписей всего приложения переустановите оригинальный Antigravity 2.28.2. Скрипт сохраняет только бинарники, а не весь `.app` и `_CodeSignature` вложенных компонентов.
