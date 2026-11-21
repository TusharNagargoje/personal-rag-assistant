import re
from typing import List, Tuple


def rewrite_conversational_query(query: str, chat_history: List[Tuple[str, str]]) -> str:
    """
    Rewrite follow-up question into a standalone search query given conversational context.
    If no history or obvious standalone query, returns query untouched.
    """
    if not chat_history:
        return query.strip()

    # Rule-based contextual pronoun expansion
    last_user_msg, last_bot_msg = chat_history[-1]
    pronouns = [" it", " that", " this", " they", " these", " those", " its", " their"]
    lower_query = f" {query.lower()} "

    has_pronoun = any(p in lower_query for p in pronouns) or len(query.split()) < 4
    if has_pronoun and last_user_msg:
        # Prepend subject keywords from previous interaction
        return f"{last_user_msg} {query}".strip()

    return query.strip()


def generate_multi_queries(query: str) -> List[str]:
    """
    Generate lexical variations of a search query for broader recall.
    """
    queries = [query.strip()]
    clean = re.sub(r"[^\w\s]", "", query).strip()
    if clean and clean != query:
        queries.append(clean)

    # Add question/factual variation
    if not query.lower().startswith(("what", "how", "why", "who", "when", "where")):
        queries.append(f"what is {query}")

    return list(dict.fromkeys(queries))[:3]
