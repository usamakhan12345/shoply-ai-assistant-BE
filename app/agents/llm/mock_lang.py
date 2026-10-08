"""Language support for the offline MockLLM: detect English / Roman Urdu / Urdu, translate the user's words into
plain English intent words (so ONE set of rules serves all three), and render replies in the user's language.

This is vocabulary-based, not real language understanding. Real LLMs (LLM_PROVIDER=openai) do this natively;
the system prompt tells them to match the user's language."""
import re

EN, RUR, UR = "en", "rur", "ur"
_URDU_SCRIPT = re.compile(r"[؀-ۿ]")

# Roman-Urdu words that are (almost) never English. One hit is enough to treat the message as Roman Urdu.
_RUR_MARKERS = set(
    """mera meri mere meray mairay mujhe mujhko mjhe kya kia kiya hai hain hy kar karo kardo karna karwa karwao krdo krna karen kijiye
    batao btao bata bataen batain batayen bataiye dikhao dikha dikhado dikhaen dikhaiye dekhao chahiye chahye chahiyen nahi nhi kahan kaha kidhar
    kitne kitni kitna kitnay konsa konsi kaunsa kaunsi kaun kon abhi wala wali wale walay yeh isko isay usko usay aap aapka aapki aapke
    pohancha pohanch pahuncha pahunch pohonch hua hui hue gaya gayi gaye dalo daalo daal dalna hatao hata kholo khol shukriya shukria meherbani
    sasta sasti saste mehnga mehngi mehnge pehla pehli pehle dusra doosra dusri teesra teesri chautha panchwa kab kaise kese kyun kyon tak
    zyada zyadah kam sab bhi lekin mene maine abh tk kharcha kharch salam salaam assalam assalamualaikum aoa magar acha achi acche theek thik karwana mangwa mangwao khareed kharid khareedna lena""".split()
)


def detect_lang(text: str) -> str:
    if _URDU_SCRIPT.search(text):
        return UR
    words = set(re.findall(r"[a-z]+", text.lower()))
    return RUR if words & _RUR_MARKERS else EN


# ------------------------------------------------------------------------------------------ normalisation
_DIACRITICS = re.compile(r"[ً-ٰٟـ]")
_PHRASES: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), r) for p, r in [
    # statuses written as verbs
    (r"deliver\s+(?:ho\s+)?(?:chuk\w*|gay\w*|hu[ae]\w*)", "delivered"),
    (r"cancel(?:l?ed)?\s+(?:ho\s+)?(?:chuk\w*|gay\w*|hu[ae]\w*)", "cancelled"),
    (r"(?:pohanch|pahunch|pohonch|pohnch|pahonch|pohch)\w*", "reached"),
    # money
    (r"(\d[\d,]*\s*(?:k|lakh)?)\s*(?:rs|rupay\w*|rupee\w*|pkr)?\s*se\s*(?:kam|km|kum|neeche|niche|andar)\b", r"under \1"),
    (r"(\d[\d,]*\s*(?:k|lakh)?)\s*(?:rs|rupay\w*|rupee\w*|pkr)?\s*se\s*(?:zyada|zyadah|ziada|ziyada|zada|upar|oopar)\b", r"over \1"),
    (r"(?:rs|pkr)\s*(\d)", r"\1"),
    # rankings
    (r"sab\s*se\s*(?:zyada|zyadah|ziada)\s*(?:rated|rating|reviewed|pasand\w*)", "top rated"),
    (r"sab\s*se\s*(?:behtar\w*|acha|achi|best)", "top rated"),
    (r"sab\s*se\s*sast\w*", "cheapest"),
    (r"sab\s*se\s*(?:mehng\w*|mahng\w*)", "most expensive"),
    (r"(?:zyada|zyadah)\s*bik\w*", "best selling"),
    # actions
    (r"order\s*(?:kar|krdo|kardo|karo|karwa\w*|karna|karen|kijiye|kerdo|kr)\w*(?:\s*(?:do|dena|den|dein|dijiye|dijye|de))?", "place order"),
    (r"(?:^|\s)(?:is|iss)\s+(wala|wali|wale|product|item|cheez|chez|order)\b", r" this \1"),
    (r"(?:cart|kart)\s*(?:me|mein|main|mai|men)\b", "cart"),
    (r"stock\s*(?:me|mein|main|mai|men)\b", "in stock"),
    (r"shukr\w+|meherban\w*", "thanks"),
    # Urdu script phrases
    (r"چیک\s*آؤٹ|چیک\s*آوٹ", "checkout"),
    (r"آرڈر\s*(?:کر\s*دو|کریں|کر\s*دیں|کرو|کردو|کرنا)", "place order"),
    (r"لیپ\s*ٹاپ", "laptop"),
    (r"سب\s*سے\s*سستا", "cheapest"),
    (r"سب\s*سے\s*مہنگا", "most expensive"),
    (r"ٹاپ\s*ریٹڈ", "top rated"),
    (r"لاگ\s*ان", "login"),
    (r"کون\s*سا|کون\s*سی|کونسا|کونسی", "which"),
    (r"ہو\s*چکے|ہو\s*چکا|ہو\s*گیا|ہو\s*گئے", ""),
]]

_ROMAN_TOKENS = {
    **dict.fromkeys("mera meri mere meray mairay".split(), "my"), **dict.fromkeys("mujhe mujhko mjhe".split(), "i"),
    **dict.fromkeys("kya kia kiya".split(), "what"), **dict.fromkeys("kaun kon konsa konsi kaunsa kaunsi".split(), "which"),
    **dict.fromkeys("kitne kitni kitnay".split(), "how many"), "kitna": "how much",
    **dict.fromkeys("kahan kaha kidhar".split(), "where"), "kab": "when", **dict.fromkeys("kaise kese kaisay".split(), "how"),
    **dict.fromkeys("kyun kyon".split(), "why"),
    **dict.fromkeys("hai hain hy he ha tha thi thay hoon ho hoga hogi gaya gayi gaye hua hui hue chuka chuke ka ki ke ko se ne tak par bhi to na zara jee ji yaar".split(), ""),
    "aur": "and", "ya": "or", "ab": "now", "abhi": "now", **dict.fromkeys("mein main mai men".split(), "in"),
    **dict.fromkeys("dal daal dalo daalo dalna dalen daalen rakho rakh".split(), "add"),
    **dict.fromkeys("hata hatao hatado htao nikal nikalo nikaal".split(), "remove"),
    **dict.fromkeys("dikhao dikha dikhado dikhaen dikhaiye dikhayen dikhana batao btao bta bata batain bataen batayen bataiye batana dekhao dekhna dekhen".split(), "show"),
    **dict.fromkeys("kholo khol kholen".split(), "open"),
    **dict.fromkeys("kar karo kardo karna karwa karwao karen kijiye kr krdo de do dena den dein dijiye".split(), ""),
    **dict.fromkeys("mangwa mangwao mangwana khareed kharid khareedna kharidna".split(), "buy"),
    **dict.fromkeys("ye yeh yahi yehi yhi iss isko isay".split(), "this"), **dict.fromkeys("us usko usay wo woh wahi same".split(), "that"),
    **dict.fromkeys("sasta sasti saste sastay".split(), "cheap"), **dict.fromkeys("mehnga mehngi mehnge mahenga".split(), "expensive"),
    **dict.fromkeys("acha achi acche achay".split(), "good"), **dict.fromkeys("behtareen behtar".split(), "best"),
    **dict.fromkeys("naya naye nayi".split(), "new"), **dict.fromkeys("akhri aakhri akhiri akhir".split(), "latest"),
    **dict.fromkeys("pehla pehli pehle pehlay".split(), "first"), **dict.fromkeys("dusra doosra dusri doosri dusre".split(), "second"),
    **dict.fromkeys("teesra teesri tisra tisri".split(), "third"), **dict.fromkeys("chautha chauthi".split(), "fourth"),
    **dict.fromkeys("panchwa panchwan panchvan".split(), "fifth"),
    **dict.fromkeys("wala wali wale walay".split(), ""), **dict.fromkeys("chahiye chahye chahiyen chahiyay".split(), "want"),
    **dict.fromkeys("nahi nhi".split(), "not"), "zyada": "more", "zyadah": "more", "kam": "less", "sab": "all",
    "salam": "hi", "assalam": "hi", "aoa": "hi",
    **dict.fromkeys("mene maine mainey".split(), "i"), "abh": "now", **dict.fromkeys("ker kr li liya lia liye lie tk".split(), ""), **dict.fromkeys("kharcha kharch".split(), "spent"),
}

_URDU_TOKENS = {
    **dict.fromkeys("میرے میرا میری مری".split(), "my"), "مجھے": "i", **dict.fromkeys("آرڈر آڈر".split(), "order"), **dict.fromkeys("آرڈرز آرڈرس".split(), "orders"),
    **dict.fromkeys("ڈیلیور ڈیلیورڈ ڈلیور ڈلیورڈ".split(), "delivered"),
    **dict.fromkeys("ہوئے ہوا ہوئی ہو چکے چکا چکی گیا گئے گئی ہے ہیں کا کی کے کو سے نے پر تک بھی تو کر کریں کرو کردو دو دیں دیجیے".split(), ""),
    **dict.fromkeys("بتاؤ بتاو بتائیں بتائیے بتادو دکھاؤ دکھاو دکھائیں دکھائیے دکھادو".split(), "show"), "کارٹ": "cart", "میں": "in",
    **dict.fromkeys("ڈال ڈالو ڈالیں ڈالدو".split(), "add"), **dict.fromkeys("نکال نکالو ہٹا ہٹاؤ ہٹادو".split(), "remove"),
    "کیا": "what", **dict.fromkeys("کتنے کتنی".split(), "how many"), "کہاں": "where", "پروڈکٹ": "product", "پروڈکٹس": "product", "چیز": "product",
    **dict.fromkeys("الیکٹرانکس الیکٹرک الیکٹرانک".split(), "electronics"), **dict.fromkeys("موبائل فون".split(), "mobile"),
    **dict.fromkeys("سستا سستی سستے".split(), "cheap"), **dict.fromkeys("مہنگا مہنگی مہنگے".split(), "expensive"),
    "بہترین": "best", **dict.fromkeys("اچھا اچھی".split(), "good"), "ٹاپ": "top", "ریٹڈ": "rated", "ریٹنگ": "rating", "قیمت": "price",
    **dict.fromkeys("پہلا پہلی پہلے".split(), "first"), **dict.fromkeys("دوسرا دوسری دوسرے".split(), "second"), **dict.fromkeys("تیسرا تیسری".split(), "third"),
    "چوتھا": "fourth", "پانچواں": "fifth", **dict.fromkeys("یہ اس اسے اسکو اسی".split(), "this"), **dict.fromkeys("وہ اُس".split(), "that"),
    **dict.fromkeys("سٹیٹس اسٹیٹس صورتحال".split(), "status"), **dict.fromkeys("آخری لیٹسٹ تازہ".split(), "latest"), **dict.fromkeys("پہنچا پہنچ پہنچی".split(), "reached"),
    "پینڈنگ": "pending", **dict.fromkeys("کینسل منسوخ".split(), "cancelled"), "اور": "and", "یا": "or", "نہیں": "not", **dict.fromkeys("چاہیے چاہئے".split(), "want"),
    "خریداری": "shopping", **dict.fromkeys("خرچ خرچہ".split(), "spent"), "اب": "now", **dict.fromkeys("کل ٹوٹل".split(), "total"), "ہیلو": "hello", "سلام": "hi", "شکریہ": "thanks", "مدد": "help", **dict.fromkeys("خریدنا خریدو خرید".split(), "buy"), "آپ": "you", "ہمارا": "our",
}


def normalise(text: str, lang: str) -> str:
    """Rewrite Roman-Urdu / Urdu into plain English intent words. English passes through untouched."""
    t = _DIACRITICS.sub("", text.lower().strip())
    if lang == EN:
        return re.sub(r"\s+", " ", t)
    for rx, rep in _PHRASES:
        t = rx.sub(rep, t)
    t = re.sub(r"[؟،۔?!]", " ", t)
    t = re.sub(r",(?=\s|$)", " ", t)
    table = _URDU_TOKENS if lang == UR else _ROMAN_TOKENS
    out = [table.get(tok, tok) for tok in t.split()]
    return re.sub(r"\s+", " ", " ".join(out)).strip()


# ------------------------------------------------------------------------------------------ reply templates
# Roman Urdu is written the way people actually type it: simple, no formal vocabulary.
_T: dict[str, dict[str, str]] = {
    "hi": {
        EN: "Hi! 👋 I can search products, check your orders, manage your cart and open the checkout for you. What do you need?",
        RUR: "Salam! 👋 Main products dhoond sakta hoon, aapke orders check kar sakta hoon, cart sambhal sakta hoon aur checkout khol sakta hoon. Bataiye kya chahiye?",
        UR: "السلام علیکم! 👋 میں پروڈکٹس تلاش کر سکتا ہوں، آپ کے آرڈرز دیکھ سکتا ہوں، کارٹ سنبھال سکتا ہوں اور چیک آؤٹ کھول سکتا ہوں۔ بتائیے کیا چاہیے؟",
    },
    "thanks": {EN: "You're welcome! Anything else I can help with?", RUR: "Koi baat nahi! Aur kuch chahiye to bata dein.", UR: "کوئی بات نہیں! اور کچھ چاہیے تو بتا دیں۔"},
    "help": {
        EN: "I can help you:\n• find products (“laptops under 120000”, “red shoes”, “cheapest kitchen appliances”)\n• show top-rated, popular or best-discounted items and product details\n• add/remove items in your cart and show it\n• check your orders (“delivered orders”, “where is my latest order?”)\n• open checkout and other pages for you\nYou can write in English, Urdu or Roman Urdu.",
        RUR: "Main in cheezon me madad kar sakta hoon:\n• products dhoondna (“laptops 120000 se kam”, “red shoes”, “sab se sasta kitchen item”)\n• top rated ya discount wale products aur details dikhana\n• cart me add/remove karna aur cart dikhana\n• aapke orders check karna (“delivered orders batao”, “mera latest order kahan hai?”)\n• checkout aur dusre pages khol dena\nAap English, Urdu ya Roman Urdu me likh sakte hain.",
        UR: "میں ان کاموں میں مدد کر سکتا ہوں:\n• پروڈکٹس تلاش کرنا اور تفصیل دکھانا\n• کارٹ میں شامل/ختم کرنا اور کارٹ دکھانا\n• آپ کے آرڈرز اور ان کی صورتحال بتانا\n• چیک آؤٹ اور دوسرے صفحات کھولنا\nآپ اردو، رومن اردو یا انگلش میں لکھ سکتے ہیں۔",
    },
    "identity": {EN: "I'm the store's AI assistant. I look things up in the real catalog and your account, and can manage your cart. How can I help?", RUR: "Main is store ka AI assistant hoon. Main asli catalog aur aapke account se maloomat dekh kar bataata hoon aur cart bhi sambhal sakta hoon. Kaise madad karun?", UR: "میں اس اسٹور کا اے آئی اسسٹنٹ ہوں۔ میں اصل کیٹلاگ اور آپ کے اکاؤنٹ سے معلومات دیکھ کر بتاتا ہوں اور کارٹ بھی سنبھال سکتا ہوں۔ کیسے مدد کروں؟"},
    "offtopic": {EN: "I'm a shopping assistant, so I can't help with that. I can find products, check your orders and manage your cart though!", RUR: "Main shopping assistant hoon, is liye is baare me madad nahi kar sakta. Products, orders aur cart ke baare me poochh sakte hain!", UR: "میں شاپنگ اسسٹنٹ ہوں اس لیے اس میں مدد نہیں کر سکتا۔ پروڈکٹس، آرڈرز اور کارٹ کے بارے میں پوچھ سکتے ہیں!"},
    "refuse": {EN: "Sorry, I can't help with that. I can only search products and manage your own cart and orders.", RUR: "Maazrat, main ye nahi kar sakta. Main sirf products dhoond sakta hoon aur aapka apna cart aur orders dekh sakta hoon.", UR: "معذرت، میں یہ نہیں کر سکتا۔ میں صرف پروڈکٹس تلاش کر سکتا ہوں اور آپ کا اپنا کارٹ اور آرڈرز دیکھ سکتا ہوں۔"},
    "other_user": {EN: "I can only access orders associated with your account.", RUR: "Main sirf aapke apne account ke orders dekh sakta hoon.", UR: "میں صرف آپ کے اپنے اکاؤنٹ کے آرڈرز دیکھ سکتا ہوں۔"},
    "cancel_decline": {EN: "I can't cancel orders from chat. Cancellation is handled by the seller; you can follow your order status under My Orders.", RUR: "Main chat se order cancel nahi kar sakta. Cancel seller karta hai; aap My Orders me apne order ka status dekh sakte hain.", UR: "میں چیٹ سے آرڈر منسوخ نہیں کر سکتا۔ یہ سیلر کرتا ہے؛ آپ My Orders میں اپنے آرڈر کی صورتحال دیکھ سکتے ہیں۔"},
    "clear_cart": {EN: "I can remove items one at a time. Ask me to show your cart, then say “remove the first one”.", RUR: "Main items ek ek karke hata sakta hoon. Pehle cart dikhane ko kahein, phir bolein “pehla wala hata do”.", UR: "میں آئٹمز ایک ایک کر کے ہٹا سکتا ہوں۔ پہلے کارٹ دکھانے کو کہیں، پھر کہیں “پہلا ہٹا دو”۔"},
    "ask_search_first": {EN: "I haven't shown you any products yet. Ask me to search for something first.", RUR: "Maine abhi tak koi product nahi dikhaya. Pehle kuch search karne ko kahein.", UR: "میں نے ابھی کوئی پروڈکٹ نہیں دکھائی۔ پہلے کچھ تلاش کرنے کو کہیں۔"},
    "ask_which_product": {EN: "Which product do you mean? Ask me to search for something first, then tell me which one.", RUR: "Kaun sa product? Pehle search karwa lein, phir bata dein kaun sa wala.", UR: "کون سی پروڈکٹ؟ پہلے تلاش کروائیں پھر بتائیں کون سی۔"},
    "ask_number": {EN: "Which one do you mean? Say a number from 1 to {n}, for example “add the second one to my cart”.", RUR: "Kaun sa wala? 1 se {n} tak number bata dein, jaise “second wala cart me dal do”.", UR: "کون سا؟ 1 سے {n} تک نمبر بتائیں، جیسے “دوسرا کارٹ میں ڈال دو”۔"},
    "out_of_range": {EN: "I only showed {n} product(s). Which number do you mean?", RUR: "Maine sirf {n} product(s) dikhaye hain. Kaun sa number?", UR: "میں نے صرف {n} پروڈکٹس دکھائی ہیں۔ کون سا نمبر؟"},
    "ask_qty": {EN: "What quantity would you like?", RUR: "Kitni quantity chahiye?", UR: "کتنی تعداد چاہیے؟"},
    "login_add": {EN: "Please log in first. Once you're logged in, I can add this product to your cart.", RUR: "Ye karne ke liye pehle login karna hoga. Login kar lein, phir main is product ko cart me add kar dunga.", UR: "اس کے لیے پہلے لاگ ان کریں۔ لاگ ان کے بعد میں یہ پروڈکٹ آپ کے کارٹ میں شامل کر دوں گا۔"},
    "login_remove": {EN: "Please log in first. Once you're logged in, I can remove items from your cart.", RUR: "Pehle login karna hoga. Login ke baad main cart se items hata dunga.", UR: "پہلے لاگ ان کریں۔ لاگ ان کے بعد میں کارٹ سے آئٹمز ہٹا دوں گا۔"},
    "login_update": {EN: "Please log in first. Once you're logged in, I can change your cart.", RUR: "Pehle login karna hoga. Login ke baad main aapka cart change kar dunga.", UR: "پہلے لاگ ان کریں۔ لاگ ان کے بعد میں آپ کا کارٹ تبدیل کر دوں گا۔"},
    "login_cart": {EN: "Please log in first. Once you're logged in, I can show your cart.", RUR: "Pehle login karna hoga. Login ke baad main aapka cart dikha dunga.", UR: "پہلے لاگ ان کریں۔ لاگ ان کے بعد میں آپ کا کارٹ دکھا دوں گا۔"},
    "login_orders": {EN: "Please log in first. Once you're logged in, I can show your orders and their status.", RUR: "Pehle login karna hoga. Login ke baad main aapke orders aur unka status bata dunga.", UR: "پہلے لاگ ان کریں۔ لاگ ان کے بعد میں آپ کے آرڈرز اور ان کی صورتحال بتا دوں گا۔"},
    "login_checkout": {EN: "Please log in first. Once you're logged in, I can take you to checkout.", RUR: "Pehle login karna hoga, phir main aapko checkout par le ja sakta hoon.", UR: "پہلے لاگ ان کریں، پھر میں آپ کو چیک آؤٹ پر لے جا سکتا ہوں۔"},
    "login_other": {EN: "Please log in first, then I can do that for you.", RUR: "Pehle login karna hoga, phir main ye kar dunga.", UR: "پہلے لاگ ان کریں، پھر میں یہ کر دوں گا۔"},
    "added": {EN: "Done. I've added {p} to your cart (quantity in cart: {q}).", RUR: "Ho gaya, maine {p} aapke cart me add kar diya hai (cart me quantity: {q}).", UR: "ہو گیا، میں نے {p} آپ کے کارٹ میں شامل کر دی ہے (کارٹ میں تعداد: {q})۔"},
    "removed": {EN: "Done. I've removed {p} from your cart.", RUR: "Ho gaya, maine {p} cart se hata diya hai.", UR: "ہو گیا، میں نے {p} کارٹ سے ہٹا دی ہے۔"},
    "updated": {EN: "Done. {p} is now quantity {q} in your cart.", RUR: "Ho gaya, ab cart me {p} ki quantity {q} hai.", UR: "ہو گیا، اب کارٹ میں {p} کی تعداد {q} ہے۔"},
    "not_in_cart": {EN: "That product isn't in your cart.", RUR: "Ye product aapke cart me nahi hai.", UR: "یہ پروڈکٹ آپ کے کارٹ میں نہیں ہے۔"},
    "cart_empty": {EN: "Your cart is empty.", RUR: "Aapka cart khali hai.", UR: "آپ کا کارٹ خالی ہے۔"},
    "cart_head": {EN: "Your cart:", RUR: "Aapka cart:", UR: "آپ کا کارٹ:"},
    "cart_total": {EN: "Total: Rs. {t} (shipping Rs. {s})", RUR: "Total: Rs. {t} (shipping Rs. {s})", UR: "کل: Rs. {t} (شپنگ Rs. {s})"},
    "orders_none": {EN: "You don't have any orders yet.", RUR: "Aapke account me abhi koi order nahi mila.", UR: "آپ کے اکاؤنٹ میں ابھی کوئی آرڈر نہیں ملا۔"},
    "orders_none_f": {EN: "You have no {f} orders.", RUR: "Aapka koi {f} order nahi hai.", UR: "آپ کا کوئی {f} آرڈر نہیں ہے۔"},
    "orders_head": {EN: "You have {n} {f} order(s):", RUR: "Aapke {n} {f} order(s) hain:", UR: "آپ کے {n} {f} آرڈر(ز) ہیں:"},
    "orders_head_any": {EN: "You have {n} order(s):", RUR: "Aapke {n} order(s) hain:", UR: "آپ کے {n} آرڈر(ز) ہیں:"},
    "orders_more": {EN: "(showing the {m} most recent)", RUR: "(sab se naye {m} dikha raha hoon)", UR: "(تازہ ترین {m} دکھا رہا ہوں)"},
    "order_status": {EN: "Your order #{id} is currently {s}.", RUR: "Aapka order #{id} abhi {s} hai.", UR: "آپ کا آرڈر #{id} اس وقت {s} ہے۔"},
    "order_delivered_yes": {EN: "Yes, your order #{id} was delivered on {d}.", RUR: "Ji haan, aapka order #{id} {d} ko deliver ho chuka hai.", UR: "جی ہاں، آپ کا آرڈر #{id} {d} کو ڈیلیور ہو چکا ہے۔"},
    "order_delivered_no": {EN: "Not yet. Your order #{id} is currently {s}.", RUR: "Abhi nahi. Aapka order #{id} abhi {s} hai.", UR: "ابھی نہیں۔ آپ کا آرڈر #{id} اس وقت {s} ہے۔"},
    "spending": {EN: "You have spent Rs. {t} in total across {n} order(s) (cancelled orders not counted).", RUR: "Aap ne ab tak {n} order(s) me total Rs. {t} ki shopping ki hai (cancelled orders shamil nahi).", UR: "آپ نے اب تک {n} آرڈر(ز) میں کل Rs. {t} کی خریداری کی ہے (منسوخ آرڈرز شامل نہیں)۔"},
    "spending_none": {EN: "You haven't spent anything yet: there are no orders on your account.", RUR: "Aap ne abhi tak koi shopping nahi ki: aapke account me koi order nahi hai.", UR: "آپ نے ابھی تک کوئی خریداری نہیں کی: آپ کے اکاؤنٹ میں کوئی آرڈر نہیں۔"},
    "order_not_found": {EN: "I couldn't find that order in your account.", RUR: "Ye order aapke account me nahi mila.", UR: "یہ آرڈر آپ کے اکاؤنٹ میں نہیں ملا۔"},
    "delivered_on": {EN: "delivered on {d}", RUR: "{d} ko deliver hua", UR: "{d} کو ڈیلیور ہوا"},
    "checkout_ready": {EN: "Your cart is ready to order. I've opened the checkout page for you. Please review your address and payment there.", RUR: "Aapka cart order ke liye tayyar hai. Maine checkout page khol diya hai, wahan address aur payment check kar lein.", UR: "آپ کا کارٹ آرڈر کے لیے تیار ہے۔ میں نے چیک آؤٹ پیج کھول دیا ہے، وہاں ایڈریس اور ادائیگی چیک کر لیں۔"},
    "checkout_ready_p": {EN: "{p} is ready to order. I've opened the checkout page for you. Please review your address and payment there.", RUR: "{p} order ke liye tayyar hai. Maine checkout page khol diya hai, wahan address aur payment check kar lein.", UR: "{p} آرڈر کے لیے تیار ہے۔ میں نے چیک آؤٹ پیج کھول دیا ہے، وہاں ایڈریس اور ادائیگی چیک کر لیں۔"},
    "checkout_empty": {EN: "Your cart is empty, so there's nothing to check out yet. Tell me which product you want and I'll set it up.", RUR: "Aapka cart khali hai, abhi checkout ke liye kuch nahi hai. Bata dein kaun sa product chahiye, main tayyar kar dunga.", UR: "آپ کا کارٹ خالی ہے، ابھی چیک آؤٹ کے لیے کچھ نہیں۔ بتائیں کون سی پروڈکٹ چاہیے، میں تیار کر دوں گا۔"},
    "nav_orders": {EN: "Opening your orders page.", RUR: "Aapke orders ka page khol raha hoon.", UR: "آپ کے آرڈرز کا صفحہ کھول رہا ہوں۔"},
    "nav_cart": {EN: "Opening your cart.", RUR: "Aapka cart khol raha hoon.", UR: "آپ کا کارٹ کھول رہا ہوں۔"},
    "nav_order": {EN: "Opening order #{id}.", RUR: "Order #{id} khol raha hoon.", UR: "آرڈر #{id} کھول رہا ہوں۔"},
    "nav_product": {EN: "Opening {p}.", RUR: "{p} ka page khol raha hoon.", UR: "{p} کا صفحہ کھول رہا ہوں۔"},
    "found": {EN: "Here is what I found:", RUR: "Ye mila hai:", UR: "یہ ملا ہے:"},
    "found_top": {EN: "Here are the top-rated {l}items:", RUR: "Ye {l}top rated items hain:", UR: "یہ {l}ٹاپ ریٹڈ آئٹمز ہیں:"},
    "found_cheap": {EN: "Here are the lowest-priced matches:", RUR: "Ye sab se sasti options hain:", UR: "یہ سب سے سستے آپشنز ہیں:"},
    "found_exp": {EN: "Here are the most expensive matches:", RUR: "Ye sab se mehngi options hain:", UR: "یہ سب سے مہنگے آپشنز ہیں:"},
    "found_pop": {EN: "Here are the most popular matches:", RUR: "Ye sab se zyada bikne wale items hain:", UR: "یہ سب سے زیادہ بکنے والے آئٹمز ہیں:"},
    "found_deals": {EN: "Here are the best deals:", RUR: "Ye sab se acchi deals hain:", UR: "یہ بہترین ڈیلز ہیں:"},
    "note_partial": {EN: "No product matched all of “{q}”. These match some of the words.", RUR: "“{q}” ke sab alfaaz se koi product nahi mila. Ye kuch alfaaz se milte hain.", UR: "“{q}” کے تمام الفاظ سے کوئی پروڈکٹ نہیں ملی۔ یہ کچھ الفاظ سے ملتی ہیں۔"},
    "note_closest": {EN: "Nothing matched “{q}” exactly. These are the closest items for your other filters.", RUR: "“{q}” bilkul nahi mila. Aapke baaqi filters ke hisaab se ye sab se qareeb items hain.", UR: "“{q}” بالکل نہیں ملا۔ آپ کے باقی فلٹرز کے لحاظ سے یہ قریب ترین آئٹمز ہیں۔"},
    "no_results": {EN: "I couldn't find any “{w}”{p} in our store. Try a different keyword, category or price range.", RUR: "Hamare store me “{w}”{p} nahi mila. Koi aur keyword, category ya price range try karein.", UR: "ہمارے اسٹور میں “{w}”{p} نہیں ملا۔ کوئی اور لفظ، کیٹیگری یا قیمت آزمائیں۔"},
    "no_results_g": {EN: "I couldn't find any matching products. Try a different keyword, category or price range.", RUR: "Koi matching product nahi mila. Koi aur keyword, category ya price range try karein.", UR: "کوئی مماثل پروڈکٹ نہیں ملی۔ کوئی اور لفظ، کیٹیگری یا قیمت آزمائیں۔"},
    "price_under": {EN: " under Rs. {x}", RUR: " Rs. {x} se kam", UR: " Rs. {x} سے کم"},
    "price_over": {EN: " over Rs. {x}", RUR: " Rs. {x} se zyada", UR: " Rs. {x} سے زیادہ"},
    "price_between": {EN: " between Rs. {a} and Rs. {b}", RUR: " Rs. {a} aur Rs. {b} ke beech", UR: " Rs. {a} اور Rs. {b} کے درمیان"},
    "which_add": {EN: "Which one should I add? Say e.g. “add the second one to my cart”.", RUR: "Kaun sa add karun? Jaise bolein “second wala cart me dal do”.", UR: "کون سی شامل کروں؟ جیسے کہیں “دوسری کارٹ میں ڈال دو”۔"},
    "which_details": {EN: "Which one? Say e.g. “details of the first one”.", RUR: "Kaun sa? Jaise bolein “pehle wale ki details batao”.", UR: "کون سی؟ جیسے کہیں “پہلی کی تفصیل بتاؤ”۔"},
    "which_remove": {EN: "Which one should I remove? Say e.g. “remove the first one”.", RUR: "Kaun sa hataun? Jaise bolein “pehla wala hata do”.", UR: "کون سی ہٹاؤں؟ جیسے کہیں “پہلی ہٹا دو”۔"},
    "which_order": {EN: "Which one should I order? Say e.g. “order the second one”.", RUR: "Kaun sa order karun? Jaise bolein “second wala order kar do”.", UR: "کون سی آرڈر کروں؟ جیسے کہیں “دوسری آرڈر کر دو”۔"},
    "cats_head": {EN: "We sell:", RUR: "Hamare paas ye categories hain:", UR: "ہمارے پاس یہ کیٹیگریز ہیں:"},
    "cats_tail": {EN: "Tell me a category to browse.", RUR: "Koi category bata dein, main dikha dunga.", UR: "کوئی کیٹیگری بتائیں، میں دکھا دوں گا۔"},
    "in_stock": {EN: "{n} in stock", RUR: "{n} stock me hain", UR: "{n} اسٹاک میں ہیں"},
    "out_stock": {EN: "out of stock", RUR: "stock me nahi hai", UR: "اسٹاک میں نہیں ہے"},
    "sold_by": {EN: "sold by {s}", RUR: "seller: {s}", UR: "سیلر: {s}"},
    "no_ratings": {EN: "No ratings yet", RUR: "Abhi koi rating nahi", UR: "ابھی کوئی ریٹنگ نہیں"},
    "off": {EN: "{d}% off", RUR: "{d}% discount", UR: "{d}% رعایت"},
    "err_stock": {EN: "Sorry, that product doesn't have enough stock, so I can't add it to your cart.", RUR: "Ye product abhi itni quantity me stock me nahi hai, is liye main ise cart me add nahi kar sakta.", UR: "یہ پروڈکٹ اتنی تعداد میں اسٹاک میں نہیں ہے اس لیے میں اسے کارٹ میں شامل نہیں کر سکتا۔"},
    "err_not_found": {EN: "Sorry, I couldn't find that.", RUR: "Maazrat, ye mujhe nahi mila.", UR: "معذرت، یہ مجھے نہیں ملا۔"},
    "err_forbidden": {EN: "Only customer accounts have a cart and orders, so I can't do that for this account.", RUR: "Cart aur orders sirf customer accounts ke hote hain, is liye main is account ke liye ye nahi kar sakta.", UR: "کارٹ اور آرڈرز صرف کسٹمر اکاؤنٹس کے ہوتے ہیں اس لیے میں اس اکاؤنٹ کے لیے یہ نہیں کر سکتا۔"},
    "err_generic": {EN: "Sorry, I couldn't do that right now. Please try again.", RUR: "Maazrat, abhi main ye nahi kar saka. Dobara koshish karein.", UR: "معذرت، ابھی میں یہ نہیں کر سکا۔ دوبارہ کوشش کریں۔"},
    "ask_clarify": {EN: "I can help you find products. Try “top rated electronics”, “laptops under 120000”, or “cheapest kitchen appliances”.", RUR: "Main products dhoondne me madad kar sakta hoon. Try karein “top rated electronics”, “laptops 120000 se kam” ya “sab se sasta kitchen item”.", UR: "میں پروڈکٹس تلاش کرنے میں مدد کر سکتا ہوں۔ آزمائیں “ٹاپ ریٹڈ الیکٹرانکس” یا “سب سے سستا کچن آئٹم”۔"},
    "shipping": {EN: "Shipping is Rs. {fee} per order, and free when an order is Rs. {free} or more. Each seller ships their own items, and you can follow progress under My Orders.", RUR: "Shipping Rs. {fee} per order hai, aur Rs. {free} ya us se zyada ke order par free hai. Har seller apne items khud bhejta hai, progress My Orders me dekh sakte hain.", UR: "شپنگ Rs. {fee} فی آرڈر ہے اور Rs. {free} یا اس سے زیادہ کے آرڈر پر مفت ہے۔ ہر سیلر اپنی چیزیں خود بھیجتا ہے، پیش رفت My Orders میں دیکھیں۔"},
    "returns": {EN: "This demo store doesn't have a returns flow yet. If a seller cancels an order before it ships, the stock is restored and the payment is marked refunded.", RUR: "Is demo store me abhi returns ka system nahi hai. Agar seller shipping se pehle order cancel kar de to stock wapis aa jata hai aur payment refunded mark ho jati hai.", UR: "اس ڈیمو اسٹور میں ابھی ریٹرن کا نظام نہیں ہے۔ اگر سیلر شپ سے پہلے آرڈر منسوخ کر دے تو اسٹاک واپس آ جاتا ہے اور ادائیگی ریفنڈ ہو جاتی ہے۔"},
    "payment": {EN: "Checkout uses a simulated payment for learning: the order is marked paid instantly and no real money is charged.", RUR: "Checkout me seekhne ke liye nakli payment hoti hai: order foran paid mark ho jata hai aur asli paisa nahi katta.", UR: "چیک آؤٹ میں سیکھنے کے لیے فرضی ادائیگی ہوتی ہے: آرڈر فوراً ادا شدہ ہو جاتا ہے اور اصل پیسے نہیں کٹتے۔"},
    "how_order": {EN: "Add items to your cart, open Cart → Proceed to checkout, enter your shipping address and place the order. Or just tell me “order this” and I'll open the checkout for you.", RUR: "Items cart me daalein, Cart → Proceed to checkout par jayen, address likhein aur order place karein. Ya mujhe bolein “ye order kar do”, main checkout khol dunga.", UR: "آئٹمز کارٹ میں ڈالیں، Cart → Proceed to checkout پر جائیں، ایڈریس لکھیں اور آرڈر کریں۔ یا مجھے کہیں “یہ آرڈر کر دو”، میں چیک آؤٹ کھول دوں گا۔"},
    "how_login": {EN: "Use Sign up (top right) to create a Customer or Seller account, or Log in if you already have one.", RUR: "Upar right me Sign up se Customer ya Seller account banayen, ya pehle se account hai to Log in karein.", UR: "اوپر دائیں Sign up سے کسٹمر یا سیلر اکاؤنٹ بنائیں، یا پہلے سے ہے تو Log in کریں۔"},
}

FILTER_LABEL = {
    "delivered": {EN: "delivered", RUR: "delivered", UR: "ڈیلیور شدہ"},
    "cancelled": {EN: "cancelled", RUR: "cancelled", UR: "منسوخ شدہ"},
    "in_progress": {EN: "pending (not yet delivered)", RUR: "pending (abhi deliver nahi hue)", UR: "زیر عمل (ابھی ڈیلیور نہیں ہوئے)"},
    "pending": {EN: "pending", RUR: "pending", UR: "پینڈنگ"},
    "processing": {EN: "processing", RUR: "processing", UR: "پروسیسنگ"},
    "shipped": {EN: "shipped", RUR: "shipped", UR: "شپ شدہ"},
    "out_for_delivery": {EN: "out for delivery", RUR: "out for delivery", UR: "ڈیلیوری کے لیے نکلے ہوئے"},
}


def tr(key: str, lang: str, **kw) -> str:
    return _T[key][lang].format(**kw)
