Разбери заявку для ИСПОЛНИТЕЛЯ. Учти описание, публичную переписку и предыдущие обращения. Ответ СТРОГО JSON:
{
  "understood": true/false,
  "summary_ru": "1 короткое предложение — суть проблемы",
  "service_key": "bp|lk|edi|kp|vpn|mail|crm|1c|other",
  "category": "код категории (NS, ORDER, auth, API, OTHER …)",
  "error_stage_ru": "где в БП: этап/раздел (1 фраза, напр. «при проведении УПД»)",
  "root_cause_ru": "техническая причина (1 фраза, напр. «асинхронность создания резервирований»)",
  "facts": ["2-5 фактов по сути — без #заявки, ServiceId и email (они уже в шапке)"],
  "has_kb_solution": true/false,
  "solution_steps_ru": ["1-3 шага для исполнителя, если есть KB"],
  "public_reply_draft_ru": "готовый текст открытого ответа ИЛИ пустая строка",
  "kb_refs": [{"title": "раздел", "url": "https://confluence.dev.iek.ru/...", "why": "..."}],
  "article_links": ["только реальные confluence.dev.iek.ru — иначе []"],
  "similar_picks": [{"id": 123, "topic": "...", "why": "...", "same_problem": true}]  (до 3, только из кандидатов)
}
Не пиши missing_info / hidden_comment_ru. Нет KB → has_kb_solution=false, public_reply_draft_ru="", kb_refs=[]. similar_picks: выбери до 3 (same_problem=true только из кандидатов).
