"""A rule-based stand-in for an LLM, so the whole agent pipeline runs offline with no API key.

IT IS NOT AN LLM. It understands a wide, but fixed, vocabulary of shopping phrasings in English, Roman Urdu and
Urdu (see mock_lang.py: messages are first translated into plain English intent words, then ONE set of rules
decides what to do). What it demonstrates is the *protocol*: it looks at the conversation, answers with either a
tool call or plain text, and after a tool result comes back it writes the final reply in the user's language -
exactly the contract a real model follows. Everything else (validation, authorization, DB access, product/order
cards, navigation actions) is the real backend code. For truly free-form language set LLM_PROVIDER=openai.

Note on guests: like a naive model, it will still *try* account tools when a guest asks. The backend refuses
before touching the DB. This shows why enforcement lives in the tool executor, not in the prompt.
"""
import json
import re
from datetime import date
from itertools import count

from app.agents.llm.base import LLMResponse, ToolCall
from app.agents.llm.mock_lang import FILTER_LABEL, detect_lang, normalise, tr
from app.core.config import get_settings

_ids = count(1)

# Words that carry no product meaning. Used to find the "interesting" words of a message.
_STOP = set(
    """a an the me my mine i you your yours we us our it its this that these those them they there here one ones
    is are am was be been do does did have has had having got get give show find list display see view browse search look looking
    for of in on to from with without and or but if so at by as into about around near some any all anything something someone
    please pls can could would will should may might want wanna need like love interested buy purchase order orders add put remove delete drop take out
    cart basket bag checkout item items product products thing things stuff kind kinds sort type types model models
    what whats which who how much many when where why tell share suggest recommend recommendation recommendations offer offers
    top best rated rating ratings highest lowest good great nice better cheap cheaper cheapest expensive costly pricey price prices priced
    popular trending selling sell sells sale sales deal deals discount discounts discounted off biggest largest most least less more
    under below over above than between within up upto max maximum min minimum least rs pkr rupee rupees budget k lakh lac
    stock available instock color colour colors colours size sizes first second third fourth fifth last
    set change update edit increase decrease quantity qty amount units unit pieces piece
    equipment gear accessories accessory supplies essentials range collection variety options option
    details detail specs spec specification specifications describe more info information
    place placed placing check proceed now open go page screen navigate visit launch status latest recent newest oldest tracking track
    reached delivered deliver delivery pending cancelled canceled processing shipped history mine
    hi hello hey ok okay yes no not only just also too very really thanks""".split()
)

_SYNONYMS = {
    "electric": "electronics", "electrical": "electronics", "electronic": "electronics", "gadget": "electronics", "gadgets": "electronics",
    "phone": "mobile-phones", "phones": "mobile-phones", "mobile": "mobile-phones", "mobiles": "mobile-phones", "smartphone": "mobile-phones", "smartphones": "mobile-phones",
    "laptop": "laptops", "laptops": "laptops", "notebook": "laptops", "computer": "laptops", "computers": "laptops",
    "headphone": "audio", "headphones": "audio", "speaker": "audio", "speakers": "audio", "earbuds": "audio", "earphones": "audio", "music": "audio", "sound": "audio",
    "appliance": "kitchen-appliances", "appliances": "kitchen-appliances", "kitchen": "kitchen-appliances", "cooking": "kitchen-appliances",
    "clothes": "fashion", "clothing": "fashion", "apparel": "fashion", "outfit": "fashion", "wear": "fashion", "dress": "womens-clothing", "dresses": "womens-clothing",
    "shoes": "footwear", "shoe": "footwear", "sneakers": "footwear", "sneaker": "footwear", "trainers": "footwear", "running": "footwear", "sandals": "footwear", "boots": "footwear",
    "sofa": "furniture", "couch": "furniture", "chair": "furniture", "chairs": "furniture", "table": "furniture", "decor": "home-decor", "decoration": "home-decor",
    "home": "home-living", "house": "home-living", "beauty": "beauty-health", "health": "beauty-health",
    "skincare": "skincare", "serum": "skincare", "cream": "skincare", "lotion": "skincare", "moisturizer": "skincare", "face": "skincare", "skin": "skincare",
    "gym": "fitness", "workout": "fitness", "exercise": "fitness", "fitness": "fitness", "yoga": "fitness", "dumbbell": "fitness", "dumbbells": "fitness",
    "sports": "sports-outdoors", "sport": "sports-outdoors", "outdoor": "sports-outdoors", "outdoors": "sports-outdoors",
    "bike": "cycling", "bikes": "cycling", "bicycle": "cycling", "bicycles": "cycling", "cycle": "cycling", "cycling": "cycling",
    "camp": "camping", "camping": "camping", "tent": "camping", "tents": "camping", "hiking": "camping", "trekking": "camping",
}
# Words that name a SPECIFIC item even though they also imply a category: "sofa" => Furniture AND keyword 'sofa',
# so we show sofas, not every chair and rug. (If nothing matches, the tool falls back to the category, with a note.)
_ITEM_TERM = {
    "sofa": "sofa", "couch": "sofa", "chair": "chair", "chairs": "chair", "dumbbell": "dumbbell", "dumbbells": "dumbbell", "tent": "tent", "tents": "tent",
    "bike": "bike", "bikes": "bike", "bicycle": "bike", "bicycles": "bike", "speaker": "speaker", "speakers": "speaker", "headphone": "headphone", "headphones": "headphone",
    "earbuds": "earbud", "earphones": "earbud", "sneakers": "sneaker", "sneaker": "sneaker", "boots": "boot", "serum": "serum", "moisturizer": "moisturizer",
    "cream": "cream", "lotion": "lotion", "dress": "kurta", "dresses": "kurta",
}
_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "last": -1}
_NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

_REFUSE = re.compile(r"\b(sql|drop table|delete from|password|token|credential|database url|db url|api key|jwt|change (the )?price|set (the )?price|update (the )?stock|make me (an )?admin|hack)\b")
_OTHER_USER = re.compile(
    r"\b(another|other|someone else'?s?|somebody else'?s?|different) (user|customer|person|account)|\buser ?[b-z0-9]\b|\b(his|her|their) orders?\b|"
    r"\b(my )?(brother|sister|friend|wife|husband|bhai|behan|dost|beta)\W*s?\b.{0,20}\border|\bkisi aur\b|\bdusre (user|bande|banday)\b|\ball (users|customers)\b.{0,15}\borders?\b"
)
_OFFTOPIC = re.compile(
    r"\b(weather|temperature outside|joke|funny|poem|story|song lyrics|movie|president|prime minister|news|football score|cricket score|bitcoin|crypto|recipe|translate|"
    r"python|javascript|java code|write (a )?(code|program|essay)|homework|capital of|who (is|was|invented)|what is the (time|date)|time is it|calculate|solve|math)\b"
)
_AMT = r"(?:rs\.?|pkr|rupees?)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|lacs?|m)?\b"
_CHECKOUT = re.compile(
    r"\b(checkout|check out|place (?:an? |my |the )?order|order (?:it|this|that|these|now)|(?:this|that|it) (?:buy|order)|buy (?:it|this|that|now)|"
    r"(?:order|buy|purchase) (?:the )?(?:first|second|third|fourth|fifth|last)\b|"
    r"i want to buy (?:it|this|that)|proceed to (?:checkout|payment|pay)|purchase (?:it|this|that)|want to order)\b"
)


def _amount(num: str, suffix: str | None) -> float:
    v = float(num.replace(",", ""))
    return v * {"k": 1_000, "lakh": 100_000, "lac": 100_000, "lacs": 100_000, "m": 1_000_000}.get(suffix or "", 1)


def _norm(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {d.strftime('%b %Y')}"


class MockLLM:
    # ================================================================== entry point
    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        last = messages[-1]
        if last["role"] == "tool":
            return self._after_tools(messages)
        return self._decide(system, last["content"])

    # ================================================================== helpers: parsing the user's words
    @staticmethod
    def _shown(system: str) -> list[tuple[int, int, str]]:
        return [(int(n), int(i), t) for n, i, t in re.findall(r"^\s+(\d+)\. \[id=(\d+)\] (.+?) - Rs\.", system, re.M)]

    @staticmethod
    def _shown_orders(system: str) -> list[tuple[int, int]]:
        return [(int(n), int(i)) for n, i in re.findall(r"^\s+(\d+)\. \[order=(\d+)\]", system, re.M)]

    @staticmethod
    def _ordinal(t: str) -> int | None:
        pos = next((n for w, n in _ORD.items() if re.search(rf"\b{w}\b", t)), None)
        if pos is None and (m := re.search(r"(?:#|number |no\.? |item )(\d+)", t)):
            pos = int(m.group(1))
        return pos

    @staticmethod
    def _intent(t: str) -> str | None:
        """checkout / remove / add / details / open - the 'do something to a specific product' intents."""
        if _CHECKOUT.search(t):
            return "checkout"
        if re.search(r"\b(remove|delete|take .* out|drop)\b", t):
            return "remove"
        refers = re.search(r"\b(cart|basket|it|this|that|these|those|them|one|first|second|third|fourth|fifth|last)\b|\b\d+(st|nd|rd|th)\b|#\d", t)
        if re.search(r"\b(add|put|buy|purchase)\b", t) and refers:
            return "add"
        if re.search(r"\b(details?|tell me (more )?about|more (info|about)|specs?|specifications?|describe|information (about|on))\b", t):
            return "details"
        if re.search(r"\b(stock|available|availability)\b", t) and re.search(r"\b(this|that|it|first|second|third|fourth|fifth|last)\b", t):
            return "details"  # "is this in stock?" is a question about one specific product
        if re.search(r"\b(open|show|view|go to|take me to|navigate to|see)\b", t) and re.search(r"\b(product|item|page)\b", t) and re.search(r"\b(this|that|first|second|third|fourth|fifth|last)\b|#\d", t):
            return "open"
        return None

    @staticmethod
    def _qty(t: str) -> int:
        if m := re.search(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:x|pcs|pieces?|units?|items?|of|more)\b", t):
            v = m.group(1)
            return max(1, min(20, int(v) if v.isdigit() else _NUMWORDS[v]))
        if m := re.search(r"\b(?:quantity|qty)\s*(?:of|to|=|:)?\s*(\d{1,2})\b", t):
            return max(1, min(20, int(m.group(1))))
        return 1

    @staticmethod
    def _keywords(t: str) -> list[str]:
        return [w for w in re.findall(r"[a-z][a-z\-]+", t) if w not in _STOP]

    def _resolve(self, t: str, shown: list[tuple[int, int, str]], lang: str) -> tuple[str, int | str | None]:
        """Which product is meant? -> ('id', pid) | ('ask', question) | ('search', None)."""
        pos = self._ordinal(t)
        if pos is not None:
            if not shown:
                return "ask", tr("ask_search_first", lang)
            idx = len(shown) if pos == -1 else pos
            hit = next((pid for n, pid, _ in shown if n == idx), None)
            return ("id", hit) if hit else ("ask", tr("out_of_range", lang, n=len(shown)))
        for _, pid, title in shown:  # the user typed (part of) the name of something we just showed
            toks = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3]
            if toks and sum(w in t for w in toks) >= min(2, len(toks)):
                return "id", pid
        if self._keywords(t):
            return "search", None  # they named something new: look it up first
        if len(shown) == 1:
            return "id", shown[0][1]
        if not shown:
            return "ask", tr("ask_which_product", lang)
        return "ask", tr("ask_number", lang, n=len(shown))

    # ================================================================== step 1: decide what to do
    def _decide(self, system: str, text: str) -> LLMResponse:
        lang = detect_lang(text)
        raw = re.sub(r"\s+", " ", text.lower().strip())
        t = normalise(text, lang)
        words = re.findall(r"[a-z']+", t)
        shown = self._shown(system)
        shown_orders = self._shown_orders(system)
        guest = "GUEST" in system

        if _REFUSE.search(t) or _REFUSE.search(raw):
            return self._say(tr("refuse", lang))
        if _OTHER_USER.search(raw) or _OTHER_USER.search(t):
            return self._say(tr("other_user", lang))
        if re.search(r"^(thanks|thank you|thx|ty|ok|okay|cool|great|awesome|nice|perfect|got it)\b", t) and len(words) <= 4:
            return self._say(tr("thanks", lang))
        if re.search(r"^(hi|hello|hey|salam|assalam\S*|yo|good (morning|afternoon|evening)|hola)\b", t) and len(words) <= 4:
            return self._say(tr("hi", lang))
        if re.search(r"^(please |pls )?(i )?(need |want )?(some )?help( me| please)?$", t) or re.search(r"\b(what can you do|what do you do|how can you help|your features|how does this work|what are you able)\b", t):
            return self._say(tr("help", lang))
        if re.search(r"\b(who are you|are you (a )?(bot|human|ai|robot|real)|your name|how are you)\b", t):
            return self._say(tr("identity", lang))
        faq = self._faq(t, lang)
        if faq:
            return self._say(faq)
        if re.search(r"\bcancel\b", t) and re.search(r"\b(order|my|this|that)\b", t):
            return self._say(tr("cancel_decline", lang))
        if _OFFTOPIC.search(t):
            return self._say(tr("offtopic", lang))

        # --- "how much have I spent / shopped in total?" -> the user's own spending total
        if re.search(
            r"\b(spent|spend|spending|expenses?|expand\w*|expend\w*|spnd|spen)\b|\bhow much (?:money|amount|cash)\b|\bmoney\b.{0,30}\b(shop\w*|paid|used|store)\b|\btotal\b.{0,25}\b(shopping|purchases?|bought|orders?|paid)\b|\b(shopping|purchases?)\b.{0,25}\btotal\b|\bhow (?:much|many)\b.{0,30}\b(shopp\w*|bought|paid|purchas\w*)\b",
            t,
        ) and not any(w in _SYNONYMS or w in _ITEM_TERM for w in re.findall(r"[a-z]+", t)):
            return self._call("get_my_spending", {})

        intent = self._intent(t)
        has_cart_word = re.search(r"\b(cart|basket|bag)\b", t)

        # --- checkout: never creates an order, only prepares the cart and opens the real checkout page
        if intent == "checkout":
            return self._checkout(t, shown, lang, guest)

        # --- navigation to pages
        if re.search(r"\b(go to|open|take me to|navigate to|visit|launch|bring up)\b|\b(page|screen)\b", t) and intent != "open":
            if has_cart_word:
                return self._call("navigate_to_cart", {})
            if re.search(r"\borders?\b", t):
                if m := self._order_id(t):
                    return self._call("navigate_to_order", {"order_id": m})
                return self._call("navigate_to_orders", {})

        # --- the user's own orders
        orders = self._orders(t, shown_orders)
        if orders:
            return orders

        if has_cart_word and re.search(r"\b(clear|empty|reset|wipe)\b", t):
            return self._say(tr("clear_cart", lang))
        if re.search(r"\b(set|change|update|make|increase|decrease|edit)\b", t) and re.search(r"\b(quantity|qty|amount|units?)\b|\bto \d+\b", t):
            kind, val = self._resolve(t, shown, lang)
            if kind == "id":
                m = re.findall(r"\b(\d{1,2})\b(?!\s*(?:st|nd|rd|th))", t)
                return self._call("update_cart_quantity", {"product_id": val, "quantity": max(1, min(20, int(m[-1])))}) if m else self._say(tr("ask_qty", lang))
            if kind == "ask":
                return self._say(str(val))
        if has_cart_word and not intent:
            return self._call("get_cart", {})
        if re.search(r"\b(categor(y|ies)|departments?|sections?|what (do you|can i|can you) (sell|buy|offer)|what.*(do you sell|available|in (the )?store))\b", t) and not self._keywords(re.sub(r"categor\w*|departments?|sections?", "", t)):
            return self._call("list_categories", {})

        if intent:
            kind, val = self._resolve(t, shown, lang)
            if kind == "ask":
                if guest and intent in ("add", "remove"):  # login is needed whichever product they mean: try, and let the backend gate refuse
                    return self._call("add_to_cart" if intent == "add" else "remove_from_cart", {})
                return self._say(str(val))
            if kind == "id":
                if intent == "add":
                    return self._call("add_to_cart", {"product_id": val, "quantity": self._qty(t)})
                return self._call({"remove": "remove_from_cart", "details": "get_product_details", "open": "navigate_to_product"}[intent], {"product_id": val})
            # kind == "search": fall through - after the lookup, _after_tools performs the action on a single match

        return self._search(system, t, lang)

    def _checkout(self, t: str, shown: list[tuple[int, int, str]], lang: str, guest: bool = False) -> LLMResponse:
        has_ref = self._ordinal(t) is not None or re.search(r"\b(this|that|it|these|those)\b", t) or self._keywords(t)
        if not has_ref:
            return self._call("start_checkout", {})  # "ab order kar do": check out whatever is in the cart
        kind, val = self._resolve(t, shown, lang)
        if kind == "id":
            return self._call("start_checkout", {"product_id": val})
        if kind == "search":
            return self._search_for_followup(t, lang)
        if not shown:  # "order this" but nothing shown: maybe the cart already has it
            return self._call("start_checkout", {})
        if guest:
            return self._call("start_checkout", {})  # refused by the backend login gate -> login prompt + button
        return self._say(tr("which_order", lang) if self._ordinal(t) is None else str(val))

    def _search_for_followup(self, t: str, lang: str) -> LLMResponse:
        kws = self._keywords(t)
        return self._call("search_products", {"query": " ".join(kws[:4]), "limit": 5}) if kws else self._say(tr("ask_which_product", lang))

    # ------------------------------------------------------------------ orders
    @staticmethod
    def _order_id(t: str) -> int | None:
        m = re.search(r"(?:#|\bord-?|\border (?:number |no\.? |id )?)\s*0*(\d{1,9})\b(?!\s*(?:st|nd|rd|th))", t)
        return int(m.group(1)) if m else None

    def _orders(self, t: str, shown_orders: list[tuple[int, int]]) -> LLMResponse | None:
        if not re.search(r"\borders?\b", t) or re.search(r"\b(add|remove|cart|basket|checkout|place order|buy)\b", t):
            return None
        if not re.search(r"\b(my|status|where|reach\w*|track\w*|latest|last|recent|newest|oldest|first|second|third|fourth|fifth|details?|deliver\w*|pending|cancel\w*|processing|shipped|how many|which|list|history|number|now|progress|current|active|ongoing)\b|#\s*\d|\bord-?\d+", t):
            return None
        if oid := self._order_id(t):
            return self._call("get_my_order", {"order_id": oid})
        pos = self._ordinal(t)
        if pos == -1:
            pos = None  # "my last order" means the most recent one, not "the last in the list I was shown"
        if pos is not None and shown_orders and re.search(r"\border\b|\bone\b", t):
            idx = len(shown_orders) if pos == -1 else pos
            if hit := next((i for n, i in shown_orders if n == idx), None):
                return self._call("get_my_order", {"order_id": hit})
        latest = re.search(r"\b(latest|last|recent|newest)\b", t)
        oldest = re.search(r"\b(oldest|first)\b", t)
        if re.search(r"\bout for delivery\b", t):
            flt = "out_for_delivery"
        elif re.search(r"\bdelivered\b", t):
            flt = "delivered"
        elif re.search(r"\bcancel(l)?ed\b", t):
            flt = "cancelled"
        elif re.search(r"\bprocessing\b", t):
            flt = "processing"
        elif re.search(r"\bshipped\b", t):
            flt = "shipped"
        elif re.search(r"\b(pending|in progress|ongoing|active|current|not delivered|undelivered|on the way|now)\b", t):
            flt = "in_progress"
        else:
            flt = "any"
        plural = re.search(r"\borders\b", t) or re.search(r"\b(how many|list|history|all)\b", t)
        wants_status = re.search(r"\b(status|where|reach\w*|track\w*)\b", t) and not re.search(r"\b(how many|list|history|all|which)\b", t)
        if wants_status and flt == "any" and not oldest:
            return self._call("get_my_order", {"which": "latest"})  # "mere orders ka status kya hai?" -> the latest order's status
        if flt == "delivered" and not re.search(r"\borders\b", t) and not re.search(r"\b(how many|list|all)\b", t):
            return self._call("get_my_order", {"which": "latest"})  # "is my order delivered yet?" -> answer for the latest order
        if latest or oldest:
            return self._call("get_my_order", {"which": "oldest" if (oldest and not latest) else "latest"})
        if plural or flt != "any":
            return self._call("get_my_orders", {"status": flt, "limit": 10 if re.search(r"how many", t) else 5})
        return self._call("get_my_order", {"which": "latest"})  # "order status?" / "where is my order?"

    def _faq(self, t: str, lang: str) -> str | None:
        """Store-policy questions, answered from the app's real rules (no DB needed)."""
        s = get_settings()
        if re.search(r"\b(shipping|delivery|deliver|delivered|dispatch)\b", t) and re.search(r"\b(cost|fee|fees|charges?|free|long|time|days|take|much|how)\b", t) and not re.search(r"\borders?\b", t):
            return tr("shipping", lang, fee=f"{s.SHIPPING_FLAT_FEE:,.0f}", free=f"{s.FREE_SHIPPING_THRESHOLD:,.0f}")
        if re.search(r"\b(return|returns|refund|refunds|exchange|replacement|warranty|money back)\b", t):
            return tr("returns", lang)
        if re.search(r"\b(payment|payments|pay|cash on delivery|cod|credit card|debit card|easypaisa|jazzcash)\b", t) and not _CHECKOUT.search(t):
            return tr("payment", lang)
        if re.search(r"\bhow\b.*\b(place|make|put|order|buy|purchase|checkout|check out)\b", t) and not re.search(r"\bhow (much|many)\b", t):
            return tr("how_order", lang)
        if re.search(r"\bhow\b.*\b(sign ?up|register|create (an )?account|log ?in|login)\b", t):
            return tr("how_login", lang)
        return None

    def _search(self, system: str, t: str, lang: str = "en") -> LLMResponse:
        slugs = re.findall(r'slug="([^"]+)" name="([^"]+)" subcategories=\[([^\]]*)\]', system)
        parent_of = {x.strip(): s for s, _, subs in slugs for x in subs.split(",") if x.strip()}
        known = {s for s, _, _ in slugs} | set(parent_of)
        words = re.findall(r"[a-z][a-z\-]+", t)

        # --- category: score every category against ALL words ("men clothing" -> mens-clothing, not just fashion)
        scores: dict[str, int] = {}
        hits: dict[str, set] = {}
        for w in words:
            if w in _STOP:
                continue
            matched = {_SYNONYMS[w]} if _SYNONYMS.get(w) in known else set()
            matched |= {k for k in known if _norm(w) in {_norm(x) for x in k.split("-")}}
            for k in matched:
                scores[k] = scores.get(k, 0) + 1
                hits.setdefault(k, set()).add(w)
        category = None
        if scores:
            top = max(scores.values())
            cands = sorted(k for k, v in scores.items() if v == top)
            subs = [c for c in cands if c in parent_of]
            if len(subs) == 1:
                category = subs[0]  # a specific subcategory beats its broad parent
            elif len(subs) > 1:
                parents = {parent_of[c] for c in subs}
                category = parents.pop() if len(parents) == 1 else subs[0]  # siblings tie -> the parent
            else:
                category = cands[0]
        used = hits.get(category, set()) if category else set()

        args: dict = {}
        if category:
            args["category"] = category

        # --- price
        if m := re.search(rf"between\s*{_AMT}\s*(?:and|to|-)\s*{_AMT}", t):
            lo, hi = _amount(m.group(1), m.group(2) or m.group(4)), _amount(m.group(3), m.group(4))
            args["min_price"], args["max_price"] = min(lo, hi), max(lo, hi)
        else:
            if m := re.search(rf"(?:under|below|less than|cheaper than|up to|upto|within|max(?:imum)?|not more than|at most|budget of)\s*{_AMT}", t):
                args["max_price"] = _amount(m.group(1), m.group(2))
            if m := re.search(rf"(?:over|above|more than|at least|min(?:imum)?|starting (?:from|at)|greater than)\s*{_AMT}", t):
                args["min_price"] = _amount(m.group(1), m.group(2))
        if re.search(r"in stock|instock|available now|currently available", t):
            args["in_stock_only"] = True

        # --- how many?
        if m := re.search(r"\b(?:top|best|first|cheapest|show|give me|list)\s*(\d{1,2})\b", t):
            args["limit"] = max(1, min(10, int(m.group(1))))

        # --- sorting
        top_rated = bool(re.search(r"top[- ]?\d*[- ]?rated|best[- ]?rated|highest[- ]?rated|best reviewed|highest rating|top rating|best reviews?|highly rated|well rated|5[- ]star", t))
        sort = None
        if re.search(r"cheapest|lowest price|low to high|least expensive|most affordable|\bcheap\b|affordable", t):
            sort = "price_asc"
        elif re.search(r"most expensive|highest price|high to low|priciest|premium|luxury", t):
            sort = "price_desc"
        elif re.search(r"best[- ]?sell|most popular|popular|trending|most sold|hot", t):
            sort = "popular"
        elif re.search(r"discount|deals?|\bsale\b|offers?|\boff\b|clearance", t):
            sort = "discount"
        elif top_rated:
            sort = "rating"
        elif re.search(r"\b(new|newest|latest|recent)\b", t):
            sort = "newest"

        # --- leftover meaningful words (brands, colours, product nouns...) become the keyword query
        keywords = [w for w in words if w not in _STOP and w not in used and w not in _SYNONYMS]
        for w in words:  # specific item nouns ("sofa") narrow the category instead of being swallowed by it
            term = _ITEM_TERM.get(w)
            if term and term not in keywords and term not in {k.rstrip("s") for k in keywords}:
                keywords.append(term)
        if keywords:
            args["query"] = " ".join(keywords[:4])

        # Questions that mention nothing shoppable ("why is the sky blue") are off-topic, not an empty search.
        question = re.match(r"^(why|what|who|when|where|how|is|are|can|could|do|does|did)\b", t)
        if question and not category and not sort and not args.keys() - {"query"}:
            if len(keywords) != 1 or re.match(r"^(why|who|when)\b", t):
                return self._say(tr("offtopic", lang))

        if not (category or keywords or sort or {"max_price", "min_price"} & args.keys()):
            return self._say(tr("ask_clarify", lang))

        if top_rated and not ({"max_price", "min_price", "query", "in_stock_only"} & args.keys()):
            return self._call("get_top_rated_products", {k: v for k, v in args.items() if k in ("category", "limit")})
        if sort:
            args["sort"] = sort
        return self._call("search_products", args)

    # ================================================================== step 2: after tool results
    def _after_tools(self, messages: list[dict]) -> LLMResponse:
        start = max(i for i, m in enumerate(messages) if m["role"] == "user")
        original = messages[start]["content"]
        lang = detect_lang(original)
        t = normalise(original, lang)
        tool_msgs = [m for m in messages[start:] if m["role"] == "tool"]

        # "add the blender to my cart" = search first, then act if the search found exactly one product.
        if len(tool_msgs) == 1 and tool_msgs[0]["name"] in ("search_products", "get_top_rated_products"):
            d = json.loads(tool_msgs[0]["content"])
            intent = self._intent(t)
            if intent and len(d.get("products", [])) == 1 and not d.get("note"):
                pid = d["products"][0]["id"]
                if intent == "add":
                    return self._call("add_to_cart", {"product_id": pid, "quantity": self._qty(t)})
                return self._call({"remove": "remove_from_cart", "details": "get_product_details", "open": "navigate_to_product", "checkout": "start_checkout"}[intent], {"product_id": pid})
        return LLMResponse(content=self._compose(messages, start, t, lang))

    def _compose(self, messages: list[dict], start: int, t: str, lang: str) -> str:
        calls = {c["id"]: c for m in messages[start:] if m["role"] == "assistant" for c in m.get("tool_calls", [])}
        parts = []
        for m in messages[start:]:
            if m["role"] != "tool":
                continue
            data = json.loads(m["content"])
            args = calls.get(m["tool_call_id"], {}).get("arguments", {})
            parts.append(self._format(m["name"], args, data, t, lang))
        return "\n\n".join(p for p in parts if p)

    @staticmethod
    def _call(name: str, args: dict) -> LLMResponse:
        return LLMResponse(tool_calls=[ToolCall(id=f"mock_{next(_ids)}", name=name, arguments=args)])

    @staticmethod
    def _say(text: str) -> LLMResponse:
        return LLMResponse(content=text)

    @staticmethod
    def _line(p: dict, lang: str) -> str:
        price = f"Rs. {p['price']:,.0f}"
        if p.get("discount_percent"):
            price += f" ({tr('off', lang, d=p['discount_percent'])})"
        rating = f"★ {p['rating']:.1f}" if p["review_count"] else tr("no_ratings", lang)
        return f"   {rating} · {price}"

    @staticmethod
    def _order_line(o: dict, lang: str) -> str:
        names = [re.sub(r"^1 x ", "", i) for i in o["items"]]  # "1 x Kettle" -> "Kettle", "2 x Kettle" stays
        items = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
        tail = tr("delivered_on", lang, d=_fmt_date(o["delivered_on"])) if o["delivered_on"] else o["status"]
        return f"#{o['order_id']} · {items} · {tail}"

    def _format(self, tool: str, args: dict, d: dict, t: str, lang: str) -> str:
        if d.get("error") == "login_required":
            key = {
                "add_to_cart": "login_add", "remove_from_cart": "login_remove", "update_cart_quantity": "login_update",
                "get_cart": "login_cart", "navigate_to_cart": "login_cart", "get_my_orders": "login_orders", "get_my_order": "login_orders", "get_my_spending": "login_orders",
                "navigate_to_orders": "login_orders", "navigate_to_order": "login_orders", "start_checkout": "login_checkout",
            }.get(tool, "login_other")
            return tr(key, lang)
        if "error" in d:  # never show raw backend messages: map the error CODE to a friendly sentence
            code = d.get("code")
            if code == "insufficient_stock":
                return tr("err_stock", lang)
            if code == "not_found":
                if tool in ("get_my_order", "navigate_to_order"):
                    return tr("order_not_found", lang)
                if tool in ("remove_from_cart", "update_cart_quantity"):
                    return tr("not_in_cart", lang)
                return tr("err_not_found", lang)
            if code == "forbidden":
                return tr("err_forbidden", lang)
            return tr("err_generic", lang)

        if tool in ("search_products", "get_top_rated_products"):
            ps = d["products"]
            if not ps:
                what = args.get("query") or (args.get("category") or "").replace("-", " ")
                price = ""
                if "max_price" in args and "min_price" in args:
                    price = tr("price_between", lang, a=f"{args['min_price']:,.0f}", b=f"{args['max_price']:,.0f}")
                elif "max_price" in args:
                    price = tr("price_under", lang, x=f"{args['max_price']:,.0f}")
                elif "min_price" in args:
                    price = tr("price_over", lang, x=f"{args['min_price']:,.0f}")
                if what or price:
                    return tr("no_results", lang, w=what or "products", p=price)
                return tr("no_results_g", lang)
            label = (args.get("category") or "").replace("-", " ")
            if d.get("note_code") == "partial_words":
                head = tr("note_partial", lang, q=d.get("query", ""))
            elif d.get("note_code") == "closest_filters":
                head = tr("note_closest", lang, q=d.get("query", ""))
            elif tool == "get_top_rated_products":
                head = tr("found_top", lang, l=f"{label} " if label else "")
            else:
                head = {"price_asc": "found_cheap", "price_desc": "found_exp", "popular": "found_pop", "discount": "found_deals"}.get(args.get("sort"))
                head = tr(head, lang) if head else tr("found", lang)
            tail = ""
            if len(ps) > 1:
                intent = self._intent(t)
                key = {"add": "which_add", "details": "which_details", "remove": "which_remove", "checkout": "which_order"}.get(intent or "")
                tail = "\n\n" + tr(key, lang) if key else ""
            return head + "\n" + "\n".join(f"{i}. {p['title']}\n{self._line(p, lang)}" for i, p in enumerate(ps, 1)) + tail
        if tool == "list_categories":
            return tr("cats_head", lang) + "\n" + "\n".join(f"• {c['name']}: " + ", ".join(s["name"] for s in c["subcategories"]) for c in d["categories"]) + "\n\n" + tr("cats_tail", lang)
        if tool == "get_product_details":
            specs = "; ".join(f"{k}: {v}" for k, v in d["specifications"].items())
            extra = ""
            if d["colors"]:
                extra += f"\nColors: {', '.join(d['colors'])}"
            if d["sizes"]:
                extra += f"\nSizes: {', '.join(d['sizes'])}"
            stock = tr("in_stock", lang, n=d["stock"]) if d["stock"] else tr("out_stock", lang)
            return f"{d['title']}\n{self._line(d, lang)} · {stock} · {tr('sold_by', lang, s=d['sold_by'])}\n{d['description']}" + (f"\nSpecs: {specs}" if specs else "") + extra
        if tool == "add_to_cart":
            return tr("added", lang, p=d["product"], q=d["quantity_in_cart"])
        if tool == "remove_from_cart":
            return tr("removed", lang, p=d["product"])
        if tool == "update_cart_quantity":
            return tr("updated", lang, p=d["product"], q=d["quantity_in_cart"])
        if tool == "get_cart":
            if not d["items"]:
                return tr("cart_empty", lang)
            lines = "\n".join(f"{i}. {x['quantity']} x {x['title']} - Rs. {x['price']:,.0f}" for i, x in enumerate(d["items"], 1))
            return f"{tr('cart_head', lang)}\n{lines}\n" + tr("cart_total", lang, t=f"{d['total']:,.0f}", s=f"{d['shipping']:,.0f}")

        if tool == "get_my_orders":
            flt = d["filter"]
            if d["total_matching_orders"] == 0:
                return tr("orders_none", lang) if flt == "any" else tr("orders_none_f", lang, f=FILTER_LABEL[flt][lang])
            head = tr("orders_head_any", lang, n=d["total_matching_orders"]) if flt == "any" else tr("orders_head", lang, n=d["total_matching_orders"], f=FILTER_LABEL[flt][lang])
            if d["total_matching_orders"] > len(d["orders"]):
                head += " " + tr("orders_more", lang, m=len(d["orders"]))
            return head + "\n" + "\n".join(self._order_line(o, lang) for o in d["orders"])
        if tool == "get_my_order":
            if not d.get("found"):
                return tr("orders_none", lang)
            if re.search(r"\bdelivered\b", t):
                return tr("order_delivered_yes", lang, id=d["order_id"], d=_fmt_date(d["delivered_on"])) if d["delivered_on"] else tr("order_delivered_no", lang, id=d["order_id"], s=d["status"])
            items = ", ".join(d["items"])
            return tr("order_status", lang, id=d["order_id"], s=d["status"]) + f"\n{items}"

        if tool == "get_my_spending":
            if d["orders_counted"] == 0:
                return tr("spending_none", lang)
            return tr("spending", lang, t=f"{d['total_spent']:,.0f}", n=d["orders_counted"])
        if tool == "start_checkout":
            if d.get("status") == "cart_empty":
                return tr("checkout_empty", lang)
            return tr("checkout_ready_p", lang, p=d["product"]) if d.get("product") else tr("checkout_ready", lang)
        if tool == "navigate_to_orders":
            return tr("nav_orders", lang)
        if tool == "navigate_to_cart":
            return tr("nav_cart", lang)
        if tool == "navigate_to_order":
            return tr("nav_order", lang, id=d["order_id"])
        if tool == "navigate_to_product":
            return tr("nav_product", lang, p=d["product"])
        return tr("err_generic", lang)
