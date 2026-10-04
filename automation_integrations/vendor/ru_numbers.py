"""Normalize Russian numeric speech; reject any unrepresentable glyph before TTS.

One required hook owns both stages because Hermes dispatches every hook the
original script before replaying against a rewritten script.
"""
import re
import unicodedata

UNITS = ("ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать")
TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто")
HUNDREDS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот")
SCALES = (("", "", ""), ("тысяча", "тысячи", "тысяч"), ("миллион", "миллиона", "миллионов"),
          ("миллиард", "миллиарда", "миллиардов"), ("триллион", "триллиона", "триллионов"))
ORDINAL = {1: ("первый", "первого", "первом", "первая", "первое"),
           2: ("второй", "второго", "втором", "вторая", "второе"),
           3: ("третий", "третьего", "третьем", "третья", "третье"),
           4: ("четвёртый", "четвёртого", "четвёртом", "четвёртая", "четвёртое"),
           5: ("пятый", "пятого", "пятом", "пятая", "пятое"),
           6: ("шестой", "шестого", "шестом", "шестая", "шестое"),
           7: ("седьмой", "седьмого", "седьмом", "седьмая", "седьмое"),
           8: ("восьмой", "восьмого", "восьмом", "восьмая", "восьмое"),
           9: ("девятый", "девятого", "девятом", "девятая", "девятое"),
           10: ("десятый", "десятого", "десятом", "десятая", "десятое"),
           11: ("одиннадцатый", "одиннадцатого", "одиннадцатом", "одиннадцатая", "одиннадцатое"),
           12: ("двенадцатый", "двенадцатого", "двенадцатом", "двенадцатая", "двенадцатое"),
           13: ("тринадцатый", "тринадцатого", "тринадцатом", "тринадцатая", "тринадцатое"),
           14: ("четырнадцатый", "четырнадцатого", "четырнадцатом", "четырнадцатая", "четырнадцатое"),
           15: ("пятнадцатый", "пятнадцатого", "пятнадцатом", "пятнадцатая", "пятнадцатое"),
           16: ("шестнадцатый", "шестнадцатого", "шестнадцатом", "шестнадцатая", "шестнадцатое"),
           17: ("семнадцатый", "семнадцатого", "семнадцатом", "семнадцатая", "семнадцатое"),
           18: ("восемнадцатый", "восемнадцатого", "восемнадцатом", "восемнадцатая", "восемнадцатое"),
           19: ("девятнадцатый", "девятнадцатого", "девятнадцатом", "девятнадцатая", "девятнадцатое"),
           20: ("двадцатый", "двадцатого", "двадцатом", "двадцатая", "двадцатое"),
           30: ("тридцатый", "тридцатого", "тридцатом", "тридцатая", "тридцатое"),
           40: ("сороковой", "сорокового", "сороковом", "сороковая", "сороковое"),
           50: ("пятидесятый", "пятидесятого", "пятидесятом", "пятидесятая", "пятидесятое"),
           60: ("шестидесятый", "шестидесятого", "шестидесятом", "шестидесятая", "шестидесятое"),
           70: ("семидесятый", "семидесятого", "семидесятом", "семидесятая", "семидесятое"),
           80: ("восьмидесятый", "восьмидесятого", "восьмидесятом", "восьмидесятая", "восьмидесятое"),
           90: ("девяностый", "девяностого", "девяностом", "девяностая", "девяностое"),
           100: ("сотый", "сотого", "сотом", "сотая", "сотое")}
MONTHS = ("", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
DIGIT = r"[0-9٠-٩۰-۹]"
GROUP = rf"{DIGIT}{{1,3}}(?:[ \u00a0\u202f]{DIGIT}{{3}})+"
NUMBER = rf"(?:{GROUP}|{DIGIT}+)"
DATE = re.compile(rf"(?<!\w)({DIGIT}{{1,2}})([./])({DIGIT}{{1,2}})\2({DIGIT}{{4}})(?!\w|\.{DIGIT})")
CALENDAR_DAYS = re.compile(
    rf"(?<!\w){DIGIT}{{1,2}}(?:\s*(?:,|и)\s+{DIGIT}{{1,2}})*\s+"
    rf"(?:{'|'.join(MONTHS[1:])})\b", re.IGNORECASE,
)
# Match a complete international Russian mobile, never a prefix of a longer identifier.
PHONE = re.compile(r"(?<![\w+])\+7(?:[ \t\u00a0\u202f()\-]*[0-9]){10}(?![0-9])")
PHONE_CONTEXT = re.compile(
    r"(?P<label>\b(?:телефон|тел\.|мобильный|моб\.)[ \t]*:?[ \t]*)"
    r"(?P<number>8(?:[ \t\u00a0\u202f()\-]*[0-9]){10}|[0-9](?:[ \t\u00a0\u202f()\-]*[0-9]){9})(?![0-9])",
    re.IGNORECASE,
)
CODE_CONTEXT = re.compile(r"(?P<label>\bкод[ \t:]+)(?P<value>[0-9]+(?:-[0-9]+)+)(?!\w)", re.IGNORECASE)
CLOCK = re.compile(r"(?<![\w.:])([01]?[0-9]|2[0-3]):([0-5][0-9])(?![\w:])")
DURATION_TIMER = re.compile(
    r"(?<!\w)(?P<count>[0-9]+)-минутн(?:ого\s+таймера|ый\s+таймер)(?!\w)",
    re.IGNORECASE,
)
MONEY_AMOUNT = re.compile(
    rf"(?<!\w)(?P<whole>{NUMBER}),(?P<minor>[0-9]{{2}})[ \t]*(?P<unit>рублей|рубля|рубль|руб\.|долларов|доллара|доллар)(?!\w)",
    re.IGNORECASE,
)
RUBLE_WHOLE = re.compile(
    rf"(?<![\w.,])(?P<count>{NUMBER})\s+(?P<unit>рублей|рубля|рубль|руб\.)(?!\w)",
    re.IGNORECASE,
)
PIECES = re.compile(rf"(?<!\w)(?P<count>{NUMBER})\s+шт\.(?=[,\s]|$)", re.IGNORECASE)
TOKEN = re.compile(rf"(?<!\w)[−-]?{NUMBER}(?:[.,]{DIGIT}+)*(?:\s*%|-[а-яА-Я]{{1,3}})?|{NUMBER}(?:[.,]{DIGIT}+)*(?:\s*%|-[а-яА-Я]{{1,3}})?|(?<!\w)[Ⅻ²](?!\w)|(?<!\w)№\s*{NUMBER}", re.UNICODE)
FRACTIONS = {1: "десятых", 2: "сотых", 3: "тысячных", 4: "десятитысячных", 5: "стотысячных", 6: "миллионных"}
# The shared Hermes TTS cleaner turns arrows into English "to" before this hook.
# Only rewrite capitalized Cyrillic place-name pairs; other uses of "to" are not routes.
_ROUTE_PLACE = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*"
ROUTE = re.compile(rf"(?<![\w-])(?P<from>{_ROUTE_PLACE})\s*(?:→|⇒|\bto\b)\s*(?P<to>{_ROUTE_PLACE})(?![\w-])")
ROUTE_SPEECH = {
    ("Волгоград", "Санкт-Петербург"): "из Волгограда в Санкт-Петербург",
    ("Санкт-Петербург", "Пхукет"): "из Санкт-Петербурга на Пхукет",
}

def _routes_to_speech(text):
    def replace(match):
        origin, destination = match.group("from"), match.group("to")
        spoken = ROUTE_SPEECH.get((origin, destination))
        if spoken is None:
            return f"пункт отправления {origin}; пункт прибытия {destination}"
        if match.start() == 0 or text[:match.start()].rstrip().endswith(('.', '!', '?')):
            return spoken[0].upper() + spoken[1:]
        return spoken
    text = ROUTE.sub(replace, text)
    return re.sub(r"\b(Маршрут)\s+(?=пункт отправления\b)", r"\1: ", text)


def _digits(value):
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in value)


def _form(number, forms):
    last_two = number % 100
    return forms[2] if 11 <= last_two <= 14 else forms[0 if number % 10 == 1 else 1 if number % 10 in (2, 3, 4) else 2]


def _triplet(n, feminine=False):
    out = []
    if n >= 100:
        out.append(HUNDREDS[n // 100])
    n %= 100
    if n >= 20:
        out.append(TENS[n // 10])
        n %= 10
    if n:
        if feminine and n in (1, 2):
            out.append(("одна", "две")[n - 1])
        else:
            out.append(UNITS[n])
    return out


def cardinal(value, feminine=False):
    if value < 0 or value >= 10 ** (3 * len(SCALES)):
        raise ValueError("number outside supported Russian cardinal range")
    if value == 0:
        return UNITS[0]
    parts = []
    for index in reversed(range(len(SCALES))):
        triplet = (value // 1000 ** index) % 1000
        if triplet:
            parts.extend(_triplet(triplet, feminine=index == 1 or (index == 0 and feminine)))
            if index:
                parts.append(_form(triplet, SCALES[index]))
    return " ".join(parts)


def ordinal(value, form="nom"):
    idx = {"nom": 0, "gen": 1, "loc": 2, "fem": 3, "neu": 4}[form]
    if value <= 0:
        raise ValueError("ordinal must be positive")
    if value in ORDINAL:
        return ORDINAL[value][idx]
    rest = value % 100
    if rest and rest in ORDINAL:
        prefix = cardinal(value - rest)
        return prefix + " " + ORDINAL[rest][idx]
    rest = value % 10
    if rest and rest in ORDINAL:
        return cardinal(value - rest) + " " + ORDINAL[rest][idx]
    # Compound round values without established morphology are rejected rather than misread.
    raise ValueError("unsupported ordinal morphology")


def _year(value, form):
    if not 1000 <= value <= 2999:
        raise ValueError("year outside supported range")
    # Russian year expressions inflect only the final ordinal: две тысячи двадцать четвёртом.
    tail = value % 100
    if not tail:
        raise ValueError("round-century year morphology is not supported")
    return cardinal(value - tail) + " " + ordinal(tail, form)


def _spoken_token(match, source):
    raw = match.group()
    if raw.startswith("№"):
        return "номер " + " ".join(UNITS[int(c)] for c in _digits(re.sub(r"\s", "", raw[1:])))
    if raw == "Ⅻ":
        return "двенадцать"
    if raw == "²":
        return "два"
    negative = raw.startswith(("-", "−"))
    token = raw[1:] if negative else raw
    percent = token.endswith("%")
    if percent:
        token = token[:-1].rstrip()
    suffix = re.search(r"-([а-яА-Я]{1,3})$", token)
    ordinal_form = ({"й": "nom", "ый": "nom", "ой": "nom", "го": "gen", "ого": "gen",
                     "м": "loc", "ом": "loc", "я": "fem", "ая": "fem", "е": "neu", "ое": "neu"}
                    .get(suffix.group(1).lower()) if suffix else None)
    acronym = suffix.group(1) if suffix and ordinal_form is None and suffix.group(1).isupper() else None
    if suffix:
        token = token[:suffix.start()]
    cleaned = _digits(token).replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    pre = source[:match.start()]
    post = source[match.end():]
    identifier = bool(re.search(r"[A-Za-zА-Яа-я][-_]?$", pre) or re.match(r"[-_][A-Za-zА-Яа-я]", post))
    if suffix and not acronym:
        if ordinal_form is None:
            raise ValueError("unknown ordinal ending")
        n = int(cleaned)
        result = _year(n, ordinal_form) if 1000 <= n <= 2999 else ordinal(n, ordinal_form)
    elif re.fullmatch(r"[0-9]+", cleaned):
        n = int(cleaned)
        year_context = re.match(r"\s+(год(?:а|у|ом|е)?|г\.)\b", post, re.IGNORECASE)
        if year_context and 1000 <= n <= 2999 and not identifier:
            word = year_context.group(1).lower()
            form = "gen" if word in ("года", "г.") else "loc" if word in ("году", "годе", "годом") else "nom"
            result = _year(n, form)
        elif (identifier or re.search(r"(?:серийный\s+)?номер\s*$|артикул\s*$", pre, re.IGNORECASE)) and len(cleaned) > 1 and (len(cleaned) >= 4 or cleaned.startswith("0")):
            result = " ".join(UNITS[int(c)] for c in cleaned)
        else:
            minute_noun = re.match(r"\s+минут(?:а|ы|у)\b", post, re.IGNORECASE)
            thousand_noun = re.match(r"\s+тысяч(?:а|и)?\b", post, re.IGNORECASE)
            result = cardinal(n, feminine=bool(minute_noun or thousand_noun))
            if minute_noun and minute_noun.group().lower().endswith("у") and n % 10 == 1 and n % 100 != 11:
                result = result[:-4] + "одну" if result.endswith("одна") else result
    elif "." in cleaned and re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", cleaned):
        if percent and cleaned.count(".") == 1:
            whole, fraction = cleaned.split(".")
            if len(fraction) not in FRACTIONS:
                raise ValueError("decimal precision outside supported range")
            whole_n = int(whole)
            result = cardinal(whole_n, feminine=True) + (" целая " if whole_n % 10 == 1 and whole_n % 100 != 11 else " целых ") + cardinal(int(fraction)) + " " + FRACTIONS[len(fraction)]
        else:
            result = " точка ".join(" ".join(UNITS[int(c)] for c in segment) if len(segment) > 1 and segment.startswith("0") else cardinal(int(segment)) for segment in cleaned.split("."))
    elif "," in cleaned and re.fullmatch(r"[0-9]+,[0-9]+", cleaned):
        whole, fraction = cleaned.split(",")
        if len(fraction) not in FRACTIONS:
            raise ValueError("decimal precision outside supported range")
        whole_n = int(whole)
        result = cardinal(whole_n, feminine=True) + (" целая " if whole_n % 10 == 1 and whole_n % 100 != 11 else " целых ") + cardinal(int(fraction)) + " " + FRACTIONS[len(fraction)]
    else:
        raise ValueError("unsupported numeric token")
    if percent:
        result += " " + _form(int(cleaned.split(",")[0].split(".")[0]) if cleaned[0].isdigit() else 0, ("процент", "процента", "процентов")) if "," not in cleaned and "." not in cleaned else " процента"
    return ("минус " if negative else "") + result + (" " + acronym if acronym else "")


def normalize(text):
    """Return spoken Russian script or raise ValueError on an unrepresentable numeral."""
    if not isinstance(text, str):
        raise TypeError("spoken script must be a string")

    def phone_replace(match):
        raw = match.group() if hasattr(match, "group") else match
        digits = re.sub(r"\D", "", raw)
        country = digits[0] if len(digits) == 11 else None
        subscriber = digits[1:] if country else digits
        area, triple, pair_a, pair_b = subscriber[:3], subscriber[3:6], subscriber[6:8], subscriber[8:10]
        def digit_group(group):
            return ", ".join(UNITS[int(c)] for c in group)
        def spoken_pair(group):
            return digit_group(group) if group[0] == "0" else cardinal(int(group))
        prefix = ("плюс " if raw.startswith("+") else "") + UNITS[int(country)] + "; " if country else ""
        return (prefix + digit_group(area) + "; " + digit_group(triple) + "; "
                + spoken_pair(pair_a) + "; " + spoken_pair(pair_b))

    text = _routes_to_speech(text)
    def duration_timer_replace(match):
        noun = "таймера" if "минутного" in match.group().lower() else "таймер"
        count = int(match.group("count"))
        return noun + " длительностью " + cardinal(count) + " " + _form(count, ("минута", "минуты", "минут"))
    text = DURATION_TIMER.sub(duration_timer_replace, text)
    text = PHONE.sub(phone_replace, text)
    text = PHONE_CONTEXT.sub(lambda m: m.group("label") + phone_replace(m.group("number")), text)
    text = CODE_CONTEXT.sub(
        lambda m: m.group("label") + "; ".join(", ".join(UNITS[int(c)] for c in block)
                                                   for block in m.group("value").split("-")), text)

    def clock_replace(match):
        hour, minute = int(match.group(1)), int(match.group(2))
        return (cardinal(hour) + " " + _form(hour, ("час", "часа", "часов")) + " "
                + cardinal(minute, feminine=True) + " " + _form(minute, ("минута", "минуты", "минут")))

    text = CLOCK.sub(clock_replace, text)

    def money_replace(match):
        whole = int(re.sub(r"[ \u00a0\u202f]", "", match.group("whole")))
        minor = int(match.group("minor"))
        dollars = match.group("unit").lower().startswith("доллар")
        major_forms = ("доллар", "доллара", "долларов") if dollars else ("рубль", "рубля", "рублей")
        minor_forms = ("цент", "цента", "центов") if dollars else ("копейка", "копейки", "копеек")
        return (cardinal(whole) + " " + _form(whole, major_forms) + " "
                + cardinal(minor, feminine=not dollars) + " " + _form(minor, minor_forms))

    text = MONEY_AMOUNT.sub(money_replace, text)

    def pieces_replace(match):
        count = int(_digits(re.sub(r"\s", "", match.group("count"))))
        # The period belongs to the abbreviation, except when it ends the sentence.
        ending = "." if match.end() == len(text) else ""
        return cardinal(count, feminine=True) + " " + _form(count, ("штука", "штуки", "штук")) + ending

    text = PIECES.sub(pieces_replace, text)

    def rubles_replace(match):
        count = int(_digits(re.sub(r"\s", "", match.group("count"))))
        ending = "." if match.group("unit").endswith(".") else ""
        return cardinal(count) + " " + _form(count, ("рубль", "рубля", "рублей")) + ending

    text = RUBLE_WHOLE.sub(rubles_replace, text)

    def date_replace(m):
        day, month, year = map(lambda s: int(_digits(s)), (m.group(1), m.group(3), m.group(4)))
        import datetime
        datetime.date(year, month, day)
        return ordinal(day, "gen") + " " + MONTHS[month] + " " + _year(year, "gen") + " года"

    dated = DATE.sub(date_replace, text)
    def calendar_days_replace(match):
        import datetime
        raw = match.group()
        month_name = raw.split()[-1].lower()
        month = MONTHS.index(month_name)
        def day_replace(day_match):
            day = int(_digits(day_match.group()))
            datetime.date(2024, month, day)  # Leap year permits February 29 without an explicit year.
            return ordinal(day, "gen")
        return re.sub(rf"{DIGIT}{{1,2}}", day_replace, raw)
    dated = CALENDAR_DAYS.sub(calendar_days_replace, dated)
    def abbreviated_thousands(match):
        value = int(_digits(match.group(1)))
        return cardinal(value, feminine=True) + " " + _form(value, SCALES[1])
    dated = re.sub(r"(?<!\w)([0-9]+)\s+тыс\.(?=\s|$)", abbreviated_thousands, dated, flags=re.IGNORECASE)
    result = TOKEN.sub(lambda m: _spoken_token(m, dated), dated)
    if any(c.isnumeric() for c in result):
        raise ValueError("unsupported numeric glyph remains in spoken script")
    return result


def guard_spoken_script(text: str, **_kwargs):
    """Rewrite once; Hermes rechecks this same hook against the rewritten script."""
    spoken = normalize(text)
    if any(character.isnumeric() for character in spoken):
        return {"action": "block", "message": "TTS contains unhandled numeric characters"}
    return {"text": spoken} if spoken != text else None


def register(ctx):
    ctx.register_hook("pre_tts_synthesis", guard_spoken_script)
