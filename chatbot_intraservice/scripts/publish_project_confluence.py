# -*- coding: utf-8 -*-
"""Публикация страницы «Чатбот IntraService: пайплайн, AI-KB и настройки» в WEBKB.

  python scripts/publish_project_confluence.py

Требует CONFLUENCE_BASE_URL + CONFLUENCE_PAT в .env.
Короткая ссылка: https://confluence.dev.iek.ru/x/ONttBw (pageId=124640056).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPACE = "WEBKB"
PARENT_ID = "124630073"
TITLE = "Чатбот IntraService: пайплайн, AI-KB и настройки"
META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"

BODY = r"""
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p><strong>Продукт.</strong> Чатбот 1 линии HelpDesk — ассистент <em>сотрудника IEK</em> для разбора заявок IntraService (<code>helpdesk.iek.local</code>). Пишет <strong>скрытый</strong> комментарий исполнителю (разбор + черновик ответа), проверяет контуры ЛК/БП, вложения, 1С; при необходимости учит AI-KB.</p>
<p><strong>ИИ:</strong> корпоративный шлюз <code>llm.iek.local</code> / Open WebUI <a href="https://chatgpt.iek.local/?model=support-dep-lk-web-helper">chatgpt.iek.local (support-dep-lk-web-helper)</a> — не внешний ChatGPT.</p>
<p><strong>Не путать</strong> с «Помощником партнёра ЛК» (каталог для внешних партнёров) — другой продукт в том же монорепозитории.</p>
<p><strong>Репозиторий:</strong> <code>chatbot_intraservice/</code> · GitHub: <code>Aendrous/iek-chatbot-intraservice</code> · эта страница: <a href="https://confluence.dev.iek.ru/x/ONttBw">https://confluence.dev.iek.ru/x/ONttBw</a></p>
<p><strong>Схема 1 линии:</strong> <ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот ИИЭК: схема 1 линии и заявка в HelpDesk" /></ac:link></p>
</ac:rich-text-body></ac:structured-macro>

<h2>1. Назначение и свод правил (зачем бот)</h2>
<p><strong>Куда нужен:</strong> линия Поддержка WEB / HelpDesk IntraService (ветки ЛК 731/732, БП 833/827 и смежные). Цель — ускорить исполнителя: за 10–20 секунд видеть суть, проверки и черновик ответа, не подменяя человека.</p>
<ul>
<li><strong>Разбор заявки</strong> → скрытый комментарий «Разбор от чатбота IEK LLM» (сервис/контур, заявитель, суть, факты, проверки lk-admin/adm/1С, контекст HD, текст для открытого ответа).</li>
<li><strong>Не дублировать работу:</strong> если заявка уже «В процессе» (27) или «Ожидание ответа» (46/120) при take — полный skip.</li>
<li><strong>Связывать дубли</strong> по заказу/счёту/GUID: поздняя → ParentId ранней; инициатор ранней → наблюдатель.</li>
<li><strong>Просрочка «До просрочки»:</strong> take + скрытый разбор (+ открытый ответ заявителю только при KB/ясном prior).</li>
<li><strong>Ответ заявителя «спасибо/заработало»:</strong> статус <strong>120</strong> (автозакрытие) + публичный комментарий; уточнение / «не помогло» → <strong>38</strong>.</li>
<li><strong>Цикл знаний:</strong> gap → черновик AI-KB → ревью человека → Confluence → corpus.</li>
</ul>

<h3>1.1. Чему научился бот (актуально)</h3>
<ul>
<li>Роутинг ЛК vs БП: API каталога ЛК (<code>mailer@iek.ru</code>, <code>products/api/join</code>) ≠ API-ключ bp.iek.ru.</li>
<li>Проверка пользователя в <strong>lk-admin</strong> (Bitrix) и <strong>adm.bp</strong>; в разборе — учётка = email, дата входа / «не заходил» → IEK ID forgot-password.</li>
<li>Предыдущие и похожие заявки по смыслу (не по общему слову); полный контекст prior в промпт.</li>
<li><strong>Вложения:</strong> скрин → VL IEK LLM; письмо <code>.msg</code>/<code>.eml</code>; документ <code>.pdf</code>/<code>.doc</code>/<code>.docx</code> → текст + IEK LLM (скан PDF — VL по страницам).</li>
<li>Локальные корпуса ЛК/БП/1С + черновики статей; формат скрытого разбора без повторов email/ServiceId.</li>
<li>Watch: новые / ответ пользователя / просрочка / обучение из закрытых; антидубль скрытых комментариев.</li>
</ul>

<h2>2. Streamlit — панель оператора (не движок)</h2>
<ac:structured-macro ac:name="note" ac:schema-version="1"><ac:rich-text-body>
<p><strong>Streamlit не обязателен</strong> для работы бота и для прода. Разбор заявок идёт через CLI и Windows Task Scheduler (или cron). Streamlit — UI управления.</p>
</ac:rich-text-body></ac:structured-macro>
<table class="wrapped"><tbody>
<tr><th>Вопрос</th><th>Ответ</th></tr>
<tr><td>Зачем</td><td>Панель оператора: тумблеры L1, ручной прогон заявки по Id, история LLM/KB, Promote черновиков — без правки JSON руками</td></tr>
<tr><td>Обязателен?</td><td><strong>Нет.</strong> Бот работает без UI через <code>watch_*.py</code> / <code>analyze_and_comment.py</code></td></tr>
<tr><td>Прод</td><td>Опционально на сервере (порт <strong>8502</strong>, только корп. сеть / reverse proxy). Движок = планировщик</td></tr>
<tr><td>Запуск UI</td><td>см. ниже</td></tr>
</tbody></table>
<p><strong>Как открыть интерфейс (демо / dev):</strong></p>
<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">powershell</ac:parameter><ac:plain-text-body><![CDATA[cd chatbot_intraservice
streamlit run app.py --server.port 8502]]></ac:plain-text-body></ac:structured-macro>
<ul>
<li><strong>Локально на машине:</strong> <a href="http://localhost:8502">http://localhost:8502</a></li>
<li><strong>С другого ПК в корпсети (ноутбук разработчика, типичный LAN):</strong> <code>http://10.1.25.17:8502</code> — IP может отличаться; смотреть <code>ipconfig</code> / вывод Streamlit «Network URL».</li>
<li>Это UI оператора для демо/разработки, <strong>не публичный интернет</strong>. На проде — тот же порт на сервере во внутренней сети IEK, желательно за reverse proxy (nginx/IIS) с ограничением по IP.</li>
<li>Автозапуск UI при входе в Windows: <code>install_scheduler.ps1 -WithStreamlit</code> (опционально; для автономии бота не нужен).</li>
</ul>

<h2>3. Как работает (пайплайн)</h2>
<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">text</ac:parameter><ac:plain-text-body><![CDATA[flowchart TD
  A[Watch / CLI / Streamlit] --> B{Gate: уже 27/46/120?}
  B -->|да| Z[SKIP]
  B -->|нет| C[Вложения VL / msg / PDF]
  C --> D[REST prefetch Confluence + corpus]
  D --> E[IEK LLM JSON-разбор gpt-oss-120b]
  E --> F{JSON ок?}
  F -->|нет| G[Fallback LLM]
  F -->|да| H[Скрытый комментарий]
  G --> H
  H --> I[+ compact / similar — опционально]
  I --> J[Пост HD / watch_user_reply / overdue]
  J --> K{Закрытие + learn?}
  K -->|да| L[learn_compare + kb_gap]
  K -->|нет| N[Готово]
  L --> N]]></ac:plain-text-body></ac:structured-macro>
<p>Текстом:</p>
<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">text</ac:parameter><ac:plain-text-body><![CDATA[Заявка HelpDesk (#id)
  → gate: уже в работе (27) / ожидание (46,120)? → SKIP (при take)
  → вложения: скрин (VL) / .msg .eml / .pdf .doc .docx → смысл IEK LLM
  → email партнёра, номера (заказ/счёт/GUID), related / prior / similar
  → 1С · lk-admin · adm.bp (если БП)
  → REST prefetch Confluence + corpus ЛК/БП/1С/CRM
  → LLM iek/gpt-oss-120b (resolve_model; confluence-agent снят)
  → скрытый «Разбор от чатбота IEK LLM»
  → --post: комментарий · ParentId · Observer · опционально take 27
  → watch_user_reply: «спасибо» → 120 + публичный; уточнение → 38
  → закрытие + gap → черновик AI-KB → ревью → Confluence → corpus]]></ac:plain-text-body></ac:structured-macro>
<p>Сколько раз бот бьёт в IEK LLM и как уменьшить: <a href="https://confluence.dev.iek.ru/x/geFtBw">IEK LLM и Confluence (MCP vs REST)</a> — § flowchart и «Можно ли уменьшить число запросов».</p>

<h2>3.1. Самообучение AI-KB (Corrective RAG)</h2>
<p>Обучение из <strong>закрытых заявок</strong>, когда в KB не было готового ответа. Подробная схема: <a href="https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124641312">Самообучение AI-KB (Corrective RAG)</a> · в git: <code>pipeline/IDEA_RAG_LEARNING.md</code> · кратко: <code>docs/pipeline/самообучение.md</code>.</p>
<ol>
<li><strong>Сравнение</strong> — <code>learn_compare.py</code>: скрытый разбор чатбота vs публичный ответ исполнителя (IEK LLM).</li>
<li><strong>Поиск статьи</strong> — локальный корпус + черновики (<code>kb_dedup.py</code>) + CQL Confluence WEBKB (<code>confluence_client.search_pages</code>).</li>
<li><strong>Вердикт IEK LLM</strong> — <code>kb_gap_llm.py</code>: <code>new</code> / <code>supplement</code> / <code>skip</code>, блок «Решение IEK LLM», маркеры <code>KB_INSERT_START/END</code> (текст без email).</li>
<li><strong>Черновик</strong> — <code>docs/черновики_статей/</code> + <code>knowledge/learned/index.json</code> → страница ревью (<code>ai-kb-draft</code>, parent <code>124640307</code>).</li>
<li><strong>Ревью</strong> — Streamlit вкладка AI-KB: превью Promote, «Отклонить» (<code>ai-kb-rejected</code>), Promote → append только KB_INSERT в «Быстрые ответы» (ЛК <code>124630014</code>, БП <code>124629661</code>).</li>
<li><strong>Журнал</strong> — <code>knowledge/learned/learning_events.jsonl</code> (compare + gap по каждой попытке learn).</li>
</ol>
<p>Триггеры: <code>pipeline_watch.py</code> (закрытие), <code>analyze_and_comment.py --learn</code>, <code>learn_from_ticket.py</code>. Master switch: <code>auto_learn_kb</code> (по умолчанию выкл).</p>
<p><strong>Не реализовано (backlog):</strong> авто-задачи Jira, кластеризация паттернов ошибок, SQLite-метрики — см. §6 в IDEA_RAG_LEARNING.md.</p>

<table class="wrapped"><tbody>
<tr><th>Режим</th><th>Кто</th><th>Что</th></tr>
<tr><td>Автономный</td><td>Task Scheduler / cron</td><td><code>watch_new</code>, <code>watch_user_reply</code>, <code>watch_overdue</code>, <code>pipeline_watch</code></td></tr>
<tr><td>CLI</td><td>человек / скрипт</td><td><code>analyze_and_comment.py &lt;id&gt; [--post]</code></td></tr>
<tr><td>UI</td><td>оператор</td><td>Streamlit :8502 — настройки и ручной прогон</td></tr>
</tbody></table>

<h2>4. API и интеграции (примеры)</h2>

<h3>4.1. IEK LLM (<code>https://llm.iek.local/v1</code>)</h3>
<p>OpenAI-совместимый chat completions. Токен: <code>IEK_LLM_TOKEN</code>. Разбор: <code>iek/gpt-oss-120b</code> (после снятия <code>iek/confluence-agent</code>); OCR/скрин: <code>iek/qwen3.5-122b-vl-int4-nothink</code>; fallback: тот же gpt-oss. Перед LLM — <strong>REST prefetch</strong> Confluence (<code>confluence_tools.py</code>). Подробно: <a href="https://confluence.dev.iek.ru/x/geFtBw">IEK LLM и Confluence (MCP vs REST)</a>.</p>
<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">bash</ac:parameter><ac:plain-text-body><![CDATA[POST https://llm.iek.local/v1/chat/completions
Authorization: Bearer <IEK_LLM_TOKEN>
Content-Type: application/json

{
  "model": "iek/gpt-oss-120b",
  "messages": [
    {"role": "system", "content": "…правила + корпус + prefetch…"},
    {"role": "user", "content": "Разбери заявку #… JSON…"}
  ],
  "temperature": 0.1,
  "stream": false
}]]></ac:plain-text-body></ac:structured-macro>
<p>UI-эквивалент для людей: <a href="https://chatgpt.iek.local/?model=support-dep-lk-web-helper">support-dep-lk-web-helper</a> (бот ходит в LiteLLM API напрямую, не в UI).</p>

<h3>4.2. IntraService HelpDesk (<code>https://helpdesk.iek.local/api</code>)</h3>
<p>Basic Auth: <code>INTRASERVICE_USER</code> / <code>INTRASERVICE_PASSWORD</code>.</p>
<ul>
<li><code>GET /task/{id}?fields=…</code> — заявка</li>
<li><code>GET /tasklifetime?taskid=</code> — переписка / статусы</li>
<li><code>GET /task?search=…</code> — поиск (prior / similar / заказ)</li>
<li><code>GET /taskfile/{fileId}</code> — вложение (скрин / .msg)</li>
<li><code>PUT /task/{id}</code> — StatusId, ExecutorIds, ParentId, ObserverIds, Deadline, ServiceId, комментарий</li>
</ul>
<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">bash</ac:parameter><ac:plain-text-body><![CDATA[GET https://helpdesk.iek.local/api/task/698074?fields=Id,Name,Description,ServiceId,StatusId,CreatorEmail,FileIds,Files
Authorization: Basic <user:password>]]></ac:plain-text-body></ac:structured-macro>
<p>У IntraService нет outbound webhook — бот <strong>поллит</strong> планировщиком.</p>

<h3>4.3. ЛК admin Bitrix (<code>lk.iek.ru</code>)</h3>
<p>Поиск партнёра по email: cookie <code>LK_ADMIN_COOKIE</code> или вход <code>LK_USER</code>/<code>LK_PASSWORD</code>.</p>
<ul>
<li><code>GET /bitrix/admin/user_admin.php?find=&lt;email&gt;&amp;find_type=email</code></li>
<li><code>GET /bitrix/admin/user_edit.php?ID=&lt;id&gt;</code> — LOGIN, EMAIL, LAST_LOGIN</li>
</ul>
<p>В скрытом разборе: <code>lk-admin: найден · учётка email · вход=…</code> (без мусорного Marketplace / без Bitrix id).</p>

<h3>4.4. adm.bp (<code>https://adm.bp.iek.ru</code>)</h3>
<p>Cookie <code>BP_ADM_COOKIE</code> (kc-access + kc-state; refresh <code>POST /api/auth/v1/refresh</code>).</p>
<ul>
<li><code>GET /api/user/v1/profiles?search=&lt;email&gt;&amp;page=1&amp;pageSize=16</code></li>
</ul>
<p>Только контур БП / явный bp.iek / IEK ID — не для чистого API каталога ЛК.</p>

<h3>4.5. Confluence WEBKB</h3>
<p><code>CONFLUENCE_PAT</code> → REST API: черновики AI-KB, эта страница проекта, корпуса быстрых ответов.</p>

<h3>4.6. Вложения: скрин, письма, документы</h3>
<ul>
<li><strong>Скрин</strong> → VL-модель: приложение (lk.iek.ru / Outlook / …) + смысл для исполнителя (не сырой OCR-дамп).</li>
<li><strong>.msg / .eml</strong> → текст письма → IEK LLM → смысл в блоке «Вложения».</li>
<li><strong>.pdf / .doc / .docx</strong> → извлечение текста (pymupdf, python-docx); скан PDF без текстового слоя — VL по 1–2 страницам.</li>
<li>Пакет <code>extract-msg</code>: точнее тема/от/кому/тело. Без него — запасной OLE-парсер (грубее, но работает).</li>
</ul>

<h2>5. Скрипты (.py) — что зачем</h2>
<table class="wrapped"><tbody>
<tr><th>Путь</th><th>Роль</th></tr>
<tr><td><code>app.py</code></td><td>Streamlit UI (настройки, ручной прогон, история)</td></tr>
<tr><td><code>scripts/analyze_and_comment.py</code></td><td>Ядро разбора одной заявки; <code>--post</code>, <code>--take-in-work</code></td></tr>
<tr><td><code>scripts/watch_new.py</code></td><td>Новые/переданные (31/38/121) → анализ</td></tr>
<tr><td><code>scripts/watch_user_reply.py</code></td><td>Ответ заявителя; благодарность → 120 + публичный комментарий</td></tr>
<tr><td><code>scripts/watch_overdue.py</code></td><td>Эскалация «До просрочки» → take + скрытый</td></tr>
<tr><td><code>scripts/pipeline_watch.py</code></td><td>Закрытые → AI-KB (если включено)</td></tr>
<tr><td><code>scripts/install_scheduler.ps1</code></td><td>Задачи Windows Scheduler (+ опц. Streamlit)</td></tr>
<tr><td><code>scripts/publish_project_confluence.py</code></td><td>Обновить эту страницу в Confluence</td></tr>
<tr><td><code>src/intraservice.py</code></td><td>Клиент HelpDesk API</td></tr>
<tr><td><code>src/assistants.py</code></td><td>Профили l1_web / bp_tickets / onec_tickets</td></tr>
<tr><td><code>src/lk_adm.py</code> / <code>bp_adm.py</code></td><td>Поиск в ЛК Bitrix / adm.bp</td></tr>
<tr><td><code>src/attachments.py</code></td><td>Скрин + .msg + PDF/DOC/DOCX → смысл IEK LLM</td></tr>
<tr><td><code>src/semantic_enrich.py</code></td><td>Prior / similar / тема / переписка</td></tr>
<tr><td><code>src/onec_client.py</code></td><td>1С: резерв в пути</td></tr>
<tr><td><code>src/kb_learning.py</code></td><td>Черновики AI-KB, gap, learn_from_task_data</td></tr>
<tr><td><code>src/learn_compare.py</code></td><td>Бот vs исполнитель (IEK LLM)</td></tr>
<tr><td><code>src/kb_gap_llm.py</code></td><td>Вердикт: статья неполна / слова для вставки</td></tr>
<tr><td><code>src/kb_dedup.py</code></td><td>Дедуп new/supplement/duplicate</td></tr>
<tr><td><code>src/learn_journal.py</code></td><td>Журнал learning_events.jsonl</td></tr>
<tr><td><code>scripts/pipeline_watch.py</code></td><td>Закрытые → AI-KB</td></tr>
<tr><td><code>scripts/sync_kb_after_review.py</code></td><td>Promote + corpus после ревью</td></tr>
</tbody></table>

<h2>6. Установка (Python)</h2>
<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">powershell</ac:parameter><ac:plain-text-body><![CDATA[cd "…\AI Assistant IEK"   # или iek-chatbot-intraservice
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# пакет чатбота (в т.ч. extract-msg для Outlook .msg):
pip install -r chatbot_intraservice\requirements.txt

cd chatbot_intraservice
copy .env.example .env
# заполнить: INTRASERVICE_*, IEK_LLM_*, CONFLUENCE_*, BP_ADM_COOKIE / LK_USER+LK_PASSWORD

# проверка
python scripts\intraservice_get_task.py 693437
python scripts\analyze_and_comment.py <id>          # dry-run
python scripts\analyze_and_comment.py <id> --post   # скрытый комментарий]]></ac:plain-text-body></ac:structured-macro>
<p><strong>Зависимости:</strong> <code>streamlit</code>, <code>requests</code>, <code>python-dotenv</code>, <code>urllib3</code>, <code>extract-msg</code> (≥0.48). Для 1С COM на Windows — V83.COMConnector той же разрядности, что Python.</p>
<p>Сеть: доступ к <code>helpdesk.iek.local</code>, <code>llm.iek.local</code>, при необходимости <code>lk.iek.ru</code>, <code>adm.bp.iek.ru</code>, <code>confluence.dev.iek.ru</code>.</p>

<h2>7. Планировщик Windows — что ставить и зачем</h2>
<p><code>powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1</code></p>
<table class="wrapped"><tbody>
<tr><th>Задача</th><th>Интервал</th><th>Зачем</th></tr>
<tr><td>IEK-IntraService-WatchNew</td><td>~15 мин</td><td>Новые заявки → разбор (пост если auto_post)</td></tr>
<tr><td>IEK-IntraService-WatchUserReply</td><td>~15 мин</td><td>Ответ заявителя / закрытие по «спасибо»</td></tr>
<tr><td>IEK-IntraService-WatchOverdue</td><td>~15 мин</td><td>Просрочка → take + скрытый разбор</td></tr>
<tr><td>IEK-IntraService-WatchLearn</td><td>~30 мин</td><td>Закрытые → черновики AI-KB</td></tr>
<tr><td>GapDigest / DraftsReview</td><td>вс 09:00</td><td>Дайджесты пробелов KB и черновиков на ревью</td></tr>
<tr><td>StreamlitUI (опц. <code>-WithStreamlit</code>)</td><td>при входе</td><td>UI :8502 — не нужен для автономии</td></tr>
</tbody></table>
<p>Проверка: <code>Get-ScheduledTask IEK-IntraService-*</code></p>

<h2>8. Куда ставить на прод</h2>
<ul>
<li><strong>Рекомендация:</strong> Windows Server или Linux VM во внутренней сети IEK (доступ к HelpDesk + LLM).</li>
<li>На проде достаточно <strong>venv + .env + планировщик/cron</strong> (четыре watch + learn). Streamlit — по желанию за reverse proxy, не в интернет.</li>
<li>Ноутбук разработчика — ок для пилота; для стабильной 1 линии лучше выделенная УЗ службы и сервер 24/7.</li>
<li>Секреты только в <code>.env</code> / секрет-хранилище; не в git. Cookie adm.bp периодически обновлять при истечении сессии.</li>
<li><strong>VLAN / VM + L0 (сеть):</strong>
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: VLAN / VM + L0 (сеть и доступы)" /></ac:link>
— чеклист для ДИТ, спека L0 и черновик firewall в свёрнутых блоках.</li>
</ul>

<h2>9. Управление дальше</h2>
<ul>
<li>Флаги: Streamlit sidebar → «Сохранить» → <code>config/settings.local.json</code> (или defaults в <code>settings.default.json</code>).</li>
<li>Корпуса: <code>knowledge/lk|bp|1c/corpus.md</code>; черновики → ревью Confluence → <code>sync_kb_after_review.py</code>.</li>
<li>Обновить эту страницу: <code>python scripts/publish_project_confluence.py</code></li>
<li>Локальный свод: <code>docs/pipeline/свод_правил_чатбота.md</code>, <code>docs/pipeline/решения.md</code>.</li>
</ul>

<h2>10. Настройки (кратко)</h2>
<table class="wrapped"><tbody>
<tr><th>Ключ</th><th>Default</th><th>Смысл</th></tr>
<tr><td><code>auto_post_comment</code></td><td>false</td><td>Автопост скрытого без CLI</td></tr>
<tr><td><code>auto_take_in_work</code></td><td>false</td><td>Take на всех новых (обычно off; take из overdue)</td></tr>
<tr><td><code>skip_if_in_progress_or_awaiting</code></td><td>true</td><td>27/46/120 → skip при take</td></tr>
<tr><td><code>link_related_on_post</code></td><td>true</td><td>ParentId дублей</td></tr>
<tr><td><code>auto_learn_kb</code></td><td>false</td><td>Master AI-KB</td></tr>
<tr><td><code>public_reply_only_if_kb</code></td><td>true</td><td>Открытый ответ заявителю только при KB</td></tr>
</tbody></table>

<h2>11. Секреты (.env)</h2>
<ul>
<li><code>INTRASERVICE_*</code>, <code>IEK_LLM_TOKEN</code>, <code>CONFLUENCE_*</code></li>
<li><code>BP_ADM_COOKIE</code>; <code>LK_ADMIN_COOKIE</code> или <code>LK_USER</code>/<code>LK_PASSWORD</code></li>
<li>опц. <code>1C_*</code> для резерва в пути</li>
</ul>
"""


def _load_env() -> None:
    for p in (ROOT / ".env", REPO / ".env"):
        if not p.is_file():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(p, override=False)
        except ImportError:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _session() -> requests.Session:
    _load_env()
    base = (os.environ.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
    pat = (os.environ.get("CONFLUENCE_PAT") or "").strip()
    if not base or not pat:
        raise SystemExit("Задайте CONFLUENCE_BASE_URL и CONFLUENCE_PAT")
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    session.base = base  # type: ignore[attr-defined]
    return session


def find_page(session: requests.Session) -> dict | None:
    cql = f'space = {SPACE} AND type = page AND title = "{TITLE}"'
    resp = session.get(
        f"{session.base}/rest/api/content/search",  # type: ignore[attr-defined]
        params={"cql": cql, "limit": 5},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return results[0] if results else None


def create_or_update(session: requests.Session) -> dict:
    existing = find_page(session)
    payload = {
        "type": "page",
        "title": TITLE,
        "space": {"key": SPACE},
        "ancestors": [{"id": PARENT_ID}],
        "body": {"storage": {"value": BODY.strip(), "representation": "storage"}},
    }
    if existing:
        page_id = existing["id"]
        meta = session.get(
            f"{session.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
            params={"expand": "version"},
            timeout=30,
        )
        meta.raise_for_status()
        version = int((meta.json().get("version") or {}).get("number") or 1)
        payload["version"] = {
            "number": version + 1,
            "message": "Свод: Corrective RAG / самообучение AI-KB, learn_compare, KB_INSERT",
        }
        resp = session.put(
            f"{session.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
            json=payload,
            timeout=90,
        )
    else:
        resp = session.post(
            f"{session.base}/rest/api/content",  # type: ignore[attr-defined]
            json=payload,
            timeout=90,
        )
    if resp.status_code >= 400:
        raise SystemExit(f"confluence_http {resp.status_code}: {resp.text[:1200]}")
    return resp.json()


def main() -> int:
    session = _session()
    data = create_or_update(session)
    page_id = data.get("id")
    link = f"{session.base}/pages/viewpage.action?pageId={page_id}"  # type: ignore[attr-defined]
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(
        json.dumps(
            {
                "page_id": str(page_id),
                "title": TITLE,
                "parent_id": PARENT_ID,
                "parent_title": "Чатбот ИИЭК: схема 1 линии и заявка в HelpDesk",
                "space": SPACE,
                "url": link,
                "short_url": "https://confluence.dev.iek.ru/x/ONttBw",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"page_id": page_id, "url": link, "short": "https://confluence.dev.iek.ru/x/ONttBw"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
