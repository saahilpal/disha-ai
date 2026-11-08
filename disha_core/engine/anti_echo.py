from __future__ import annotations

import re
from typing import Sequence

# ---------------------------------------------------------------------------
# Echo & Boilerplate Patterns
# ---------------------------------------------------------------------------

# Patterns that match introductory echo clauses (to strip from start of sentence)
ECHO_CLAUSE_PREFIXES = (
    # English inquiry echoes: matches full introductory clause up to comma / colon
    re.compile(
        r"^(?:(?:regarding|to\s+answer|in\s+response\s+to|answering)\s+your\s+question(?:\s+(?:about|on|regarding))?[^,!?]*[,!?]\s*|"
        r"(?:as\s+you\s+(?:mentioned|asked|noted|stated)|"
        r"you\s+(?:mentioned|asked|noted|stated|said)(?:\s+(?:that|about|whether|if))?)[^,!?]*[,!?]\s*)",
        re.I,
    ),
    # Hinglish & Hindi inquiry echoes
    re.compile(
        r"^(?:(?:aapne|apne)\s+(?:poocha|pucha|bataya|kaha|likha)\s+(?:tha\s+|hai\s+)?ki\s*|"
        r"jaise\s+ki\s+(?:aapne|apne)\s+(?:poocha|pucha|bataya|kaha)\s*[,]?\s*(?:ki\s*)?|"
        r"(?:aap|ap)\s+(?:keh|bol)\s+rahe\s+hain\s+ki\s*|"
        r"jahan\s+tak\s+aapke\s+(?:sawaal|sawal|prashn)\s+ki\s+baat\s+hai\s*[,]?\s*|"
        r"आपने\s+(?:पूछा|बताया|कहा)\s+(?:था\s+|है\s+)?कि\s*|"
        r"जैसा\s+कि\s+आपने\s+(?:पूछा|बताया|कहा)\s*[,]?\s*(?:कि\s*)?)",
        re.I,
    ),
    # Empathy boilerplate clauses
    re.compile(
        r"^(?:(?:main\s+)?samajh\s+sak(?:ta|ti)\s+hoon\s+ki\s*|"
        r"(?:mujhe\s+)?samajh\s+aa\s+raha\s+hai\s+ki\s*|"
        r"sunkar\s+(?:dukh|bura|acha|khushi)\s+(?:hua|laga)\s+ki\s*|"
        r"(?:मैं\s+)?समझ\s+सकती\s+हूँ\s+कि\s*|"
        r"सुनकर\s+(?:दुख|बुरा|अच्छा)\s+हुआ\s+कि\s*|"
        r"i\s+(?:completely\s+)?understand\s+(?:that|how)?\s*(?:you\s+(?:are|have\s+been|feel))?\s*|"
        r"i\s+hear\s+(?:that|what\s+you\s+are\s+saying)\s*[,]?\s*)",
        re.I,
    ),
)

# Connectors often following an echo clause (e.g. "...ki pet dard hai, toh...")
POST_ECHO_CONNECTORS = re.compile(
    r"^(?:toh|to|so|then|aur|and|lekin|but|isliye|therefore)\s*[,]?\s*",
    re.I,
)

# Full-sentence pure empathy / boilerplate fillers (without substantive answer)
PURE_FILLER_PATTERNS = (
    re.compile(
        r"^(?:i\s+(?:completely\s+)?understand\s+(?:that\s+)?you\s+(?:have\s+been\s+|are\s+)?feeling\s+[^.!?]+[.!?]?\s*)$",
        re.I,
    ),
    re.compile(
        r"^(?:i\s+hear\s+(?:how\s+(?:hard|difficult|tiring)\s+that\s+is|what\s+you\s+are\s+going\s+through)[.!?]?\s*)$",
        re.I,
    ),
    re.compile(
        r"^(?:(?:main\s+)?samajh\s+sak(?:ta|ti)\s+hoon\s+ki\s+(?:aap\s+)?(?:kaisa\s+mehsoos\s+kar\s+rahe\s+hain|kitna\s+mushkil\s+hai)[.!?]?\s*)$",
        re.I,
    ),
    re.compile(
        r"^(?:sunkar\s+(?:bura|dukh)\s+laga\s+ki\s+aapki\s+tabiyat\s+theek\s+nahi\s+hai[.!?]?\s*)$",
        re.I,
    ),
    re.compile(
        r"^(?:main\s+disha\s+hoon[,\.]?\s*aapki\s+ai\s+health\s+coach[.!?]?\s*)$",
        re.I,
    ),
)

# Redundant greetings / introductory boilerplate
GREETING_PREFIX_PATTERNS = re.compile(
    r"^(?:(?:namaste|hello|hi)[!.]?\s*(?:main\s+disha\s+hoon[^\.\!\?]*)?[\.\!\?]?\s*|"
    r"aapka\s+swagat\s+hai[^\.\!\?]*[\.\!\?]?\s*|"
    r"(?:theek\s+hai|thank\s+you|dhanyawad|shukriya)[,\.]?\s*)",
    re.I,
)

# Clinical safety signals: never strip or discard these!
CLINICAL_SAFETY_RE = re.compile(
    r"\b(?:doctor|clinician|hospital|clinic|112|ambulance|emergency|nursing\s+home|"
    r"prescrib(?:e|ing|tion)|medication|dawai|dawa|aspataal|daktar|chikitsak|consult)\b",
    re.I,
)


def is_clinical_safety_statement(sentence: str) -> bool:
    """Check if the sentence contains essential clinical safety instructions or referrals."""
    return bool(CLINICAL_SAFETY_RE.search(sentence))


def clean_sentence_casing(text: str) -> str:
    """Ensure stripped text begins with an uppercase letter."""
    text = text.strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def strip_all_greetings(text: str) -> str:
    """Repeatedly strip greetings until none remain."""
    cur = text.strip()
    while True:
        nxt = GREETING_PREFIX_PATTERNS.sub("", cur).strip()
        if nxt == cur or not nxt:
            return nxt
        cur = nxt


def strip_echo_prefix(sentence: str, user_text: str | None = None) -> str:
    """
    Remove parroting and introductory boilerplate clauses from the beginning of a sentence.
    Leaves the core factual answer intact.
    """
    text = sentence.strip()
    if not text:
        return ""

    # 1. Check known echo clause regexes
    for pattern in ECHO_CLAUSE_PREFIXES:
        match = pattern.match(text)
        if match:
            prefix = match.group(0)
            remainder = text[len(prefix):].strip()
            # If the remainder starts with user statement echo + connector, handle it
            if user_text:
                norm_user = " ".join(user_text.casefold().split())
                user_tokens = norm_user.split()
                if len(user_tokens) >= 3:
                    user_phrase = " ".join(user_tokens[:min(6, len(user_tokens))])
                    if remainder.casefold().startswith(user_phrase):
                        boundary_match = re.search(r"[,!?।]\s*", remainder)
                        if boundary_match and boundary_match.start() < len(user_phrase) + 30:
                            remainder = remainder[boundary_match.end():].strip()
            # Strip connector after echo (e.g. "toh", "so")
            remainder = POST_ECHO_CONNECTORS.sub("", remainder).strip()
            if remainder:
                return clean_sentence_casing(remainder)

    # 2. Check for verbatim quoting of user text at start
    if user_text:
        norm_user = " ".join(user_text.casefold().split())
        cleaned_user = re.sub(r"[^\w\s]", "", norm_user).strip()
        norm_sent = text.casefold()
        if len(cleaned_user) > 10 and norm_sent.startswith(cleaned_user):
            after_user = text[len(cleaned_user):].strip()
            after_user = re.sub(r"^[,:\-\s]+", "", after_user).strip()
            after_user = POST_ECHO_CONNECTORS.sub("", after_user).strip()
            if after_user:
                return clean_sentence_casing(after_user)

    return text


def is_pure_echo_or_filler(sentence: str, user_text: str | None = None) -> bool:
    """
    Determine if an entire sentence is pure empathy boilerplate, redundant greeting,
    or a complete parroting echo of the user's question without answering it.
    """
    text = sentence.strip()
    if not text:
        return True

    # Never treat a clinical safety statement as filler
    if is_clinical_safety_statement(text):
        return False

    # Check against known pure filler patterns
    for pattern in PURE_FILLER_PATTERNS:
        if pattern.match(text):
            return True

    # Check if sentence is purely greetings (e.g. "Namaste! Main Disha hoon. Aapka swagat hai.")
    if not strip_all_greetings(text):
        return True

    # Check if the sentence is just parroting the user input
    if user_text:
        norm_user = " ".join(re.sub(r"[^\w\s]", "", user_text.casefold()).split())
        norm_sent = " ".join(re.sub(r"[^\w\s]", "", text.casefold()).split())
        if norm_sent and norm_user:
            if norm_sent == norm_user:
                return True
            for pattern in ECHO_CLAUSE_PREFIXES:
                if pattern.match(text):
                    cleaned_sent = pattern.sub("", text).strip()
                    cleaned_norm = " ".join(re.sub(r"[^\w\s]", "", cleaned_sent.casefold()).split())
                    if cleaned_norm in norm_user or norm_user in cleaned_norm:
                        return True

    return False


def sanitize_opening_sentence(
    sentence: str,
    user_text: str | None = None,
    has_history: bool = False,
) -> str:
    """
    Sanitize the initial sentence of a turn:
    - Strips redundant greetings if conversation already has turns.
    - Strips echo prefixes so the direct answer is placed in the very first sentence.
    """
    text = sentence.strip()
    if not text:
        return ""

    if has_history:
        text = strip_all_greetings(text)

    text = strip_echo_prefix(text, user_text)
    return text


def filter_response_sentences(
    sentences: Sequence[str],
    user_text: str,
    has_history: bool = False,
) -> list[str]:
    """
    Turn-level post-processor that:
    1. Removes leading pure empathy / echo filler sentences so sentence 1 is the direct answer.
    2. Strips echo prefixes and redundant greetings from the first emitted sentence.
    3. Guarantees that at least one valid answer sentence is returned.
    """
    cleaned: list[str] = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If we have not yet added an answer sentence, check if this candidate is pure filler
        if not cleaned:
            if is_pure_echo_or_filler(sentence, user_text):
                continue
            sanitized = sanitize_opening_sentence(sentence, user_text, has_history=has_history)
            if sanitized:
                cleaned.append(sanitized)
            continue

        cleaned.append(sentence)

    # Fallback: if all sentences were dropped as filler, restore sanitized original
    if not cleaned and sentences:
        fallback = sanitize_opening_sentence(sentences[0], user_text, has_history=has_history)
        if fallback:
            cleaned.append(fallback)
        else:
            cleaned.append(sentences[0])

    return cleaned
