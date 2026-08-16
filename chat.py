# -*- coding: utf-8 -*-
"""CLI помощника партнёра ЛК на GigaChat (не chatgpt.iek.local, не виджет ЛК).

  python chat.py "Как создать заказ в ЛК?"
  python chat.py --repl
"""
from __future__ import annotations

import argparse
import sys

from gigachat_client import GigaChatClient, has_credentials, load_env
from rag import system_prompt


def ask(question: str, temperature: float = 0.15) -> str:
    load_env()
    if not has_credentials():
        raise SystemExit("Задайте GIGACHAT_AUTHORIZATION_KEY в .env (см. .env.example)")
    client = GigaChatClient()
    return client.chat(
        [
            {"role": "system", "content": system_prompt(question)},
            {"role": "user", "content": question},
        ],
        temperature=temperature,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Помощник партнёра ЛК (GigaChat)")
    parser.add_argument("question", nargs="?", help="Вопрос партнёра")
    parser.add_argument("--repl", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.15)
    args = parser.parse_args()
    load_env()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if args.repl or not args.question:
        print("Помощник партнёра ЛК (GigaChat). Пустая строка — выход.")
        client = GigaChatClient()
        while True:
            try:
                q = input("Партнёр> ").strip()
            except EOFError:
                break
            if not q:
                break
            print(client.chat(
                [
                    {"role": "system", "content": system_prompt(q)},
                    {"role": "user", "content": q},
                ],
                temperature=args.temperature,
            ))
            print()
        return 0
    print(ask(args.question, args.temperature))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
