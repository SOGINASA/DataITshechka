---
language:
- kk
license: cc-by-4.0
task_categories:
- question-answering
- text-generation
- text-classification
task_ids:
- language-modeling
- extractive-qa
pretty_name: Kazakh Customer Support QA
size_categories:
- n<1K
tags:
- kazakh
- nlp
- central-asia
- customer-support
- dialogue
- qa
- instruction-tuning
- banking
- telecom
- low-resource
---

# Dataset Card for `kazakh-customer-support-qa`

![License](https://img.shields.io/badge/license-CC%20BY%204.0-blue)
![Language](https://img.shields.io/badge/language-Kazakh%20(kk)-brightgreen)
![Size](https://img.shields.io/badge/sample%20size-406%20rows-orange)
![Full dataset](https://img.shields.io/badge/full%20dataset-~10K%20rows-lightgrey)
![Maintained by](https://img.shields.io/badge/maintained%20by-mangi--llm-yellow)
![Domain](https://img.shields.io/badge/domain-customer%20support-purple)

**Maintained by:** [Mäñgi ÜTM](https://huggingface.co/mangi-llm) (`mangi-llm`)

---

## Dataset Summary

`kazakh-customer-support-qa` is a small, hand-curated **question–answer dataset in the Kazakh language**, built to represent realistic customer-support conversations across several industries (banking, telecom, retail/service centers, sales, and general support). Each record pairs a short customer **question** with a concise, policy-safe **answer**, and many answers include **placeholder slots** (e.g. `{{ORG}}`, `{{TARIFF}}`) that a downstream system is expected to fill in with organization-specific values at inference time.

The dataset was created by the **Mäñgi ÜTM** community — an open community dedicated to Kazakh-language large language models, collecting and sharing Kazakh-language datasets. Its mission is described by the organization as: *"to gather and share Kazakh-language data, with the goal of making the Kazakh language permanent (mäñgi) in the digital space."*

This dataset is intended primarily as:
- Fine-tuning / instruction data for Kazakh-language customer-support chatbots and virtual assistants.
- A benchmark resource for evaluating **Kazakh generative and understanding capabilities** of LLMs in a real-world, domain-specific setting (see [Benchmarking](#benchmarking--suggested-evaluation-tasks) below).

> ⚠️ **This is a partial public sample.** The release published here (406 records) is a subset of a larger original dataset of **~10,000 question–answer pairs**. This sample is **free to use for everyone — including commercial use** (fine-tuning, products, research, etc.), **provided the original author is credited** (see [License](#licensing-information), CC BY 4.0). For access to the full ~10K dataset, please contact **kurumika@gmail.com** to discuss licensing — the full version is expected to be offered under a **paid license**, while this public sample remains free/open under attribution.

---

## Supported Tasks

| Task | Description | Suggested metric |
|---|---:|---|
| **Answer Generation (QA)** | Given a customer `question`, generate a helpful, on-policy `answer` (with slots left as placeholders or filled). | ROUGE-L, chrF, BLEU, human/LLM-judge helpfulness & policy-adherence scoring |
| **Domain Classification** | Predict the `domain` (6 classes) from the `question`. | Accuracy, macro-F1 |
| **Subdomain Classification** | Predict the `subdomain` (37 classes) from the `question`. | Accuracy, macro-F1 |
| **Intent Detection** | Predict the fine-grained `intent` label. | Accuracy@k (see caveat below) |
| **Slot / Placeholder Extraction** | Identify which slot types (`ORG`, `TARIFF`, `DATE`, `AMOUNT`, `CHANNEL`, `ORDER_ID`, `CONTACT`) an answer requires, or fill them given context. | Exact match, slot-level F1 |
| **Response Safety / Policy Adherence** | Using the `support/bot_policy` and `support/privacy` subsets, evaluate whether a model avoids over-promising, hallucinating, or leaking unsupported claims. | Rule-based / LLM-judge scoring |

---

## Benchmarking — Suggested Evaluation Tasks

Because this dataset is compact and richly annotated (`domain`, `subdomain`, `intent`, `slots`), it lends itself to several distinct benchmark protocols. Below is a step-by-step methodology a practitioner could follow:

### 1. Task type selection
Decide which capability you are benchmarking:
- **Generation quality** (does the model produce a fluent, correct, safe Kazakh answer given only the question?) — the primary intended use.
- **Classification quality** (domain/subdomain/intent recognition) — useful for routing/triage systems.
- **Slot awareness** (does the model recognize that an `{{ORG}}`-style placeholder is needed, rather than hallucinating a specific bank/company name?) — useful for hallucination/faithfulness testing.

### 2. Protocol for generation benchmarking
1. Hold out the `answer` field; feed the model only `question` (optionally plus `domain`/`subdomain` as system context).
2. Generate a response.
3. Score against the reference `answer` with surface metrics (ROUGE-L / chrF, since Kazakh is morphologically rich and word-overlap metrics like BLEU are less reliable) **and** an LLM-judge rubric checking: (a) factual/policy safety — does it avoid inventing concrete numbers, dates, or organization names where the reference used a placeholder; (b) fluency and grammaticality in Kazakh; (c) helpfulness/completeness.
4. Report scores broken down **by domain** (banking, telecom, service_center, sales, support, billing), since difficulty and required precision vary substantially (e.g. banking/loans answers must be more conservative than sales/negotiation answers).

### 3. Protocol for classification benchmarking
- Because each `intent` label currently appears **exactly once** in the dataset (406 rows → 406 unique intents), this field is **not directly usable as a supervised intent-classifier training/eval split** without augmentation (paraphrasing each question to create multiple examples per intent). It is, however, useful as an **open-set / zero-shot intent-labeling benchmark**: give the model the taxonomy of `domain` → `subdomain` → `intent` names and ask it to classify unseen questions, then score against gold labels.
- `domain` (6 classes, imbalanced — see distribution table) and `subdomain` (37 classes) are directly usable for standard classification benchmarking with a simple train/test split.

### 4. Protocol for slot/hallucination benchmarking
1. Present the model with the `question` only.
2. Check whether the generated answer:
   - Correctly avoids stating a concrete organization name, tariff, date, or amount when the gold answer uses a placeholder for that slot, **or**
   - Explicitly asks the user for the missing information (as several gold answers do, e.g. `ORDER_ID`, `CONTACT`).
3. This directly tests a model's calibration/faithfulness rather than fluency — a common weak point for smaller or less-aligned LLMs.

### Distribution of examples (for stratified benchmarking)

**By domain:**

| Domain | Count | Share |
|---|---:|---:|
| banking | 141 | 34.7% |
| telecom | 75 | 18.5% |
| support | 69 | 17.0% |
| service_center | 58 | 14.3% |
| sales | 47 | 11.6% |
| billing | 16 | 3.9% |
| **Total** | **406** | **100%** |

**Top subdomains by size:**

| Domain | Subdomain | Count |
|---|---|---:|
| support | general | 36 |
| banking | cards | 25 |
| banking | loans | 21 |
| sales | negotiation | 20 |
| banking | account | 17 |
| banking | terminology | 17 |
| service_center | repair | 17 |
| telecom | tariff | 15 |
| telecom | internet | 14 |
| billing | general | 14 |
| banking | transfers | 15 |
| banking | deposits | 12 |
| support | bot_policy | 12 |
| service_center | orders | 12 |

*(37 subdomains total across the six domains; see [Data Fields](#data-fields) for the full taxonomy per domain.)*

**Slot usage (records that require filling a placeholder):**

| Slot | Count |
|---|---:|
| `ORG` | 100 |
| `TARIFF` | 5 |
| `DATE` | 3 |
| `AMOUNT` | 2 |
| `CHANNEL` | 1 |
| `ORDER_ID` | 1 |
| `CONTACT` | 1 |

112 of 406 records (27.6%) contain at least one slot; the remaining 294 (72.4%) are fully self-contained answers with no placeholders.

---

## Dataset Structure

### Data Instances

```json
{
  "id": "kk-000001",
  "lang": "kk",
  "domain": "banking",
  "subdomain": "account",
  "intent": "account_open_docs",
  "question": "Шот ашу үшін қандай құжаттар керек?",
  "answer": "Әдетте жеке басты куәландыратын құжат пен ЖСН қажет. Қосымша талаптар болуы мүмкін, сондықтан нақты тізімді {{ORG}} ресми арналарынан нақтылаған дұрыс.",
  "slots": ["ORG"]
}
```

### Data Fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique record identifier, format `kk-000001`…`kk-000406`. |
| `lang` | string | Language code; currently always `"kk"` (Kazakh). |
| `domain` | string | One of 6 top-level domains: `banking`, `telecom`, `service_center`, `sales`, `support`, `billing`. |
| `subdomain` | string | One of 37 fine-grained subdomains (e.g. `cards`, `tariff`, `repair`, `negotiation`, `bot_policy`). |
| `intent` | string | Fine-grained intent label, unique per record in the current release. |
| `question` | string | The customer's question, in Kazakh (average 5.8 words, range 2–12). |
| `answer` | string | The reference support answer, in Kazakh (average 20.4 words, range 6–33), possibly containing placeholder slots. |
| `slots` | list[string] | Which placeholder types (if any) appear in `answer`, drawn from `{ORG, TARIFF, DATE, AMOUNT, CHANNEL, ORDER_ID, CONTACT}`. Empty list if the answer needs no substitution. |

### Data Splits

The dataset is currently released as a **single unsplit file** (`dataset_1_.jsonl`, 406 records, one JSON object per line, UTF-8). No official train/validation/test split is provided. Users benchmarking classification tasks should create their own stratified split (e.g. by `domain`) and are encouraged to hold out a fixed test slice for reproducible comparisons.

- Total records: **406**
- No duplicate questions or answers were found in the current release.
- All records have a unique `id`.

---

## Dataset Creation

### Curation Rationale

The dataset was assembled to fill a gap in openly available **Kazakh-language, domain-specific conversational data**, which is scarce compared to English or Russian. It focuses on customer-support scenarios because these are high-value, well-bounded use cases for deploying Kazakh-speaking assistants in real businesses (banks, telecom operators, retail service centers), while remaining safe to release publicly (no real personal or organizational data — sensitive fields are abstracted into `{{PLACEHOLDER}}` slots).

### Source Data

Answers appear to be manually written/templated by the curators (short, generic, policy-safe phrasing; consistent register; no verbatim scraped web content), rather than scraped from real support transcripts.

### Personal and Sensitive Information

The dataset does not appear to contain real personal data. Organization names, exact tariffs, dates, amounts, and contact details are deliberately abstracted into placeholder tokens (`{{ORG}}`, `{{TARIFF}}`, etc.) rather than referencing real entities.

---

## Considerations for Using the Data

### Limitations

- **Small size** (406 records) — sufficient for few-shot prompting, light instruction-tuning, or evaluation, but too small alone for training a model from scratch.
- **One example per intent** — the `intent` field cannot be used out-of-the-box as a conventional supervised classification label set without augmentation/paraphrase expansion.
- **Domain imbalance** — `banking` (34.7%) is heavily overrepresented relative to `billing` (3.9%); stratify or reweight when training/evaluating.
- **Templated style** — answers follow a consistent, somewhat formal "generic support agent" register; models trained only on this data may not generalize to more casual or emotionally charged real user messages.
- **Placeholders require downstream resolution** — any system trained on this data must implement separate logic for substituting `{{ORG}}`/`{{TARIFF}}`/etc. with real values, or explicitly preserve them for a templating layer.

### Recommended Uses
- Kazakh instruction-tuning / SFT data augmentation for support bots.
- Few-shot prompting reference set for Kazakh LLM evaluation.
- Benchmarking Kazakh fluency, hallucination-avoidance, and domain/subdomain classification of LLMs.

---

## Licensing Information

- **This public sample (406 records): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)** — free to use by anyone, for **any purpose including commercial use** (fine-tuning, products, research, redistribution, etc.), **as long as the original author/organization (Mäñgi ÜTM / `mangi-llm`) is credited**.
- **Full dataset (~10,000 pairs):** Not publicly released under this license. This sample is only a subset of the complete collection. To request access to the full dataset, contact **kurumikaz@gmail.com** to discuss terms — the full version is expected to be offered under a **separate, paid license**.
- If you use this dataset, please include a citation or attribution line pointing back to `mangi-llm` / this dataset repository (see [Citation](#citation-information)).

## Citation Information

```
@misc{kazakh_customer_support_qa,
  title = {kazakh-customer-support-qa},
  author = {Mäñgi ÜTM (mangi-llm community)},
  year = {2025},
  howpublished = {\url{https://huggingface.co/mangi-llm}}
}
```

## About the Curating Organization

**Mäñgi ÜTM** (`mangi-llm`) is an open community focused on Kazakh-language large language models. It gathers and shares Kazakh-language datasets, with the stated mission of making the Kazakh language permanent (*mäñgi* — "eternal") in the digital space.

---
---

# Датасет карточкасы: `kazakh-customer-support-qa` (қазақша)

![Лицензия](https://img.shields.io/badge/лицензия-CC%20BY%204.0-blue)
![Тіл](https://img.shields.io/badge/тіл-Қазақша%20(kk)-brightgreen)
![Көлемі](https://img.shields.io/badge/үлгі%20көлемі-406%20жол-orange)
![Толық датасет](https://img.shields.io/badge/толық%20датасет-~10%20мың%20жол-lightgrey)
![Қолдаушы](https://img.shields.io/badge/қолдаушы-mangi--llm-yellow)
![Домен](https://img.shields.io/badge/домен-клиентерге%20қолдау-purple)

**Қолдаушы ұйым:** [Mäñgi ÜTM](https://huggingface.co/mangi-llm) (`mangi-llm`)

---

## Датасет туралы қысқаша

`kazakh-customer-support-qa` — бірнеше салада (банк ісі, телеком, бөлшек сауда/қызмет көрсету орталықтары, сату, жалпы қолдау) клиенттерге қолдау көрсету диалогтарын бейнелейтін, қолмен құрастырылған шағын **қазақ тіліндегі сұрақ-жауап датасеті**. Әрбір жазба қысқа клиенттік **сұрақты** ықшам, саясатқа сай **жауаппен** байланыстырады, және көптеген жауаптарда орындаушы жүйе нақты мәндермен (ұйым атауы, тариф, т.б.) толтыруы тиіс **плейсхолдер-слоттар** (мысалы, `{{ORG}}`, `{{TARIFF}}`) бар.

Датасетті **Mäñgi ÜTM** қауымдастығы құрастырды — бұл қазақ тіліндегі ірі тілдік модельдерге қызығатын, қазақи датасеттерді жинайтын және бөлісетін ашық қауымдастық. Мақсаты — ұйымның өз сипаттамасында айтылғандай: *"қазақ тілін сандық кеңістікте мәңгілеу"*.

Бұл датасет ең алдымен мыналар үшін арналған:
- Қазақ тіліндегі клиенттерге қолдау көрсету чат-боттары мен виртуалды көмекшілерді дәл баптау (fine-tuning) / нұсқаулық деректері ретінде.
- LLM-дердің **қазақ тіліндегі генеративті және түсіну қабілетін** нақты пәндік салада бағалауға арналған бенчмарк ресурсы ретінде (төмендегі [Бенчмаркинг](#бенчмаркинг--ұсынылатын-бағалау-тапсырмалары) бөлімін қараңыз).

> ⚠️ **Бұл — толық емес, жария үлгі.** Мұнда жарияланған нұсқа (406 жазба) шын мәнінде **шамамен 10 000 сұрақ-жауап жұбынан** тұратын үлкенірек түпнұсқа датасеттің бір бөлігі ғана. Бұл үлгі **барлығына, соның ішінде коммерциялық мақсатта да, толықтай тегін пайдалануға болады** (fine-tuning, өнімдер, зерттеу және т.б.), **тек түпнұсқа авторы көрсетілу шартымен** (қараңыз: [Лицензия](#лицензия-туралы-ақпарат), CC BY 4.0). Толық ~10 мың жазбадан тұратын датасетке қол жеткізу үшін лицензия шарттарын талқылау мақсатында **kurumika@gmail.com** мекенжайына хабарласыңыз — толық нұсқа, сірә, **ақылы лицензиямен** ұсынылады деп күтілуде, ал бұл жария үлгі атрибуция талабымен тегін/ашық болып қалады.

---

## Қолдау көрсетілетін тапсырма түрлері

| Тапсырма | Сипаттамасы | Ұсынылатын метрика |
|---|---:|---|
| **Жауап генерациялау (QA)** | Клиенттің `question` сұрағы бойынша пайдалы, саясатқа сай `answer` генерациялау (слоттар плейсхолдер күйінде қалдырылуы немесе толтырылуы мүмкін). | ROUGE-L, chrF, BLEU, адам/LLM-судья бағалауы |
| **Домен классификациясы** | `question` бойынша `domain` (6 класс) анықтау. | Accuracy, macro-F1 |
| **Субдомен классификациясы** | `question` бойынша `subdomain` (37 класс) анықтау. | Accuracy, macro-F1 |
| **Интент анықтау** | Толық емес детальды `intent` белгісін анықтау. | Accuracy@k (төмендегі ескертпені қараңыз) |
| **Слот/плейсхолдер табу** | Жауапта қандай слот түрлері (`ORG`, `TARIFF`, `DATE`, `AMOUNT`, `CHANNEL`, `ORDER_ID`, `CONTACT`) қажет екенін анықтау немесе контекст бойынша толтыру. | Exact match, слот деңгейіндегі F1 |
| **Жауап қауіпсіздігі / саясатқа сәйкестік** | `support/bot_policy` мен `support/privacy` жиынтықтарын пайдаланып, модельдің артық уәде бермеуін, өтірік ақпарат тудырмауын тексеру. | Ереже негізінде / LLM-судья бағалауы |

---

## Бенчмаркинг — ұсынылатын бағалау тапсырмалары

Бұл датасет ықшам әрі бай аннотацияланған (`domain`, `subdomain`, `intent`, `slots`) болғандықтан, бірнеше бөлек бенчмарк протоколына қолайлы. Мамандар қолдана алатын қадамдық әдістеме төменде келтірілген:

### 1. Тапсырма түрін таңдау
Не бағалайтыныңызды шешіңіз:
- **Генерация сапасы** (модель тек сұрақ негізінде дұрыс, қауіпсіз қазақша жауап бере ала ма?) — негізгі мақсат.
- **Классификация сапасы** (домен/субдомен/интентті тану) — маршруттау/триаж жүйелері үшін пайдалы.
- **Слотты сезіну** (модель `{{ORG}}` секілді плейсхолдер қажет екенін таниды ма, әлде нақты банк/компания атын ойдан шығарады ма?) — галлюцинация/сенімділікті тексеруге пайдалы.

### 2. Генерацияны бенчмарктеу протоколы
1. `answer` өрісін жасырыңыз; модельге тек `question` (қаласаңыз, жүйелік контекст ретінде `domain`/`subdomain` қосып) беріңіз.
2. Жауап генерациялаңыз.
3. Эталон `answer`-мен салыстырып, беттік метрикалармен бағалаңыз (ROUGE-L / chrF — қазақ тілі морфологиялық жағынан бай болғандықтан BLEU секілді сөз-сәйкестік метрикалары аз сенімді) **және** LLM-судья критерийлерімен: (а) фактілік/саясаттық қауіпсіздік — эталонда плейсхолдер қолданылған жерде нақты сан, күн немесе ұйым атын ойдан шығармауы; (ә) қазақ тіліндегі жатықтық пен грамматикалық дұрыстық; (б) пайдалылық/толықтық.
4. Нәтижелерді **домен бойынша** бөліп беріңіз (banking, telecom, service_center, sales, support, billing), себебі қиындық пен қажетті дәлдік домендер арасында айтарлықтай өзгереді (мысалы, banking/loans жауаптары sales/negotiation-ға қарағанда әлдеқайда сақтықпен берілуі керек).

### 3. Классификацияны бенчмарктеу протоколы
- Қазіргі уақытта әрбір `intent` белгісі датасетте **тек бір рет** кездеседі (406 жол → 406 бірегей интент), сондықтан бұл өріс қосымша аугментациясыз (әр сұрақты бірнеше рет парафраздау арқылы әр интентке бірнеше мысал жасамай) **әдеттегі оқытылатын интент-классификатор үшін тікелей пайдаланылмайды**. Дегенмен, ол **ашық жиынды / zero-shot интент белгілеу бенчмаркі** ретінде пайдалы: модельге `domain` → `subdomain` → `intent` атауларының таксономиясын беріп, көрмеген сұрақтарды жіктетіп, эталон белгілермен салыстырыңыз.
- `domain` (6 класс, теңгерімсіз — таралу кестесін қараңыз) пен `subdomain` (37 класс) стандартты train/test бөлумен тікелей классификация бенчмаркингіне жарамды.

### 4. Слот/галлюцинация бенчмаркингі протоколы
1. Модельге тек `question` беріңіз.
2. Генерацияланған жауапты тексеріңіз:
   - Эталон жауапта плейсхолдер қолданылған жерде модель нақты ұйым атын, тарифті, күнді немесе соманы дұрыс айтпай ма, **немесе**
   - Кейбір эталон жауаптардағыдай (мысалы, `ORDER_ID`, `CONTACT`), жетіспейтін ақпаратты пайдаланушыдан нақты сұрайды ма.
3. Бұл модельдің жатықтығын емес, калибрация/сенімділігін тікелей тексереді — кіші немесе аз туралантылған (aligned) модельдер үшін жиі кездесетін әлсіз тұс.

### Мысалдардың таралуы (стратификацияланған бенчмаркинг үшін)

**Домен бойынша:**

| Домен | Саны | Үлесі |
|---|---:|---:|
| banking | 141 | 34.7% |
| telecom | 75 | 18.5% |
| support | 69 | 17.0% |
| service_center | 58 | 14.3% |
| sales | 47 | 11.6% |
| billing | 16 | 3.9% |
| **Барлығы** | **406** | **100%** |

**Ең үлкен субдомендер:**

| Домен | Субдомен | Саны |
|---|---|---:|
| support | general | 36 |
| banking | cards | 25 |
| banking | loans | 21 |
| sales | negotiation | 20 |
| banking | account | 17 |
| banking | terminology | 17 |
| service_center | repair | 17 |
| telecom | tariff | 15 |
| telecom | internet | 14 |
| billing | general | 14 |
| banking | transfers | 15 |
| banking | deposits | 12 |
| support | bot_policy | 12 |
| service_center | orders | 12 |

*(барлығы 6 доменде 37 субдомен бар; толық таксономия үшін [Деректер өрістері](#деректер-өрістері) бөлімін қараңыз.)*

**Слот қолданысы (плейсхолдер толтыруды қажет ететін жазбалар):**

| Слот | Саны |
|---|---:|
| `ORG` | 100 |
| `TARIFF` | 5 |
| `DATE` | 3 |
| `AMOUNT` | 2 |
| `CHANNEL` | 1 |
| `ORDER_ID` | 1 |
| `CONTACT` | 1 |

406 жазбаның 112-і (27.6%) кемінде бір слотты қамтиды; қалған 294-і (72.4%) — плейсхолдерсіз, толық дербес жауаптар.

---

## Датасет құрылымы

### Деректер мысалы

```json
{
  "id": "kk-000001",
  "lang": "kk",
  "domain": "banking",
  "subdomain": "account",
  "intent": "account_open_docs",
  "question": "Шот ашу үшін қандай құжаттар керек?",
  "answer": "Әдетте жеке басты куәландыратын құжат пен ЖСН қажет. Қосымша талаптар болуы мүмкін, сондықтан нақты тізімді {{ORG}} ресми арналарынан нақтылаған дұрыс.",
  "slots": ["ORG"]
}
```

### Деректер өрістері

| Өріс | Түрі | Сипаттамасы |
|---|---|---|
| `id` | string | Бірегей жазба идентификаторы, форматы `kk-000001`…`kk-000406`. |
| `lang` | string | Тіл коды; қазіргі уақытта әрдайым `"kk"` (қазақ тілі). |
| `domain` | string | 6 негізгі домендердің бірі: `banking`, `telecom`, `service_center`, `sales`, `support`, `billing`. |
| `subdomain` | string | 37 детальды субдомендердің бірі (мысалы, `cards`, `tariff`, `repair`, `negotiation`, `bot_policy`). |
| `intent` | string | Детальды интент белгісі, ағымдағы шығарылымда әр жазба үшін бірегей. |
| `question` | string | Клиенттің қазақ тіліндегі сұрағы (орташа 5.8 сөз, диапазоны 2–12). |
| `answer` | string | Қазақ тіліндегі эталон жауап (орташа 20.4 сөз, диапазоны 6–33), плейсхолдер слоттар болуы мүмкін. |
| `slots` | list[string] | `answer`-де кездесетін плейсхолдер түрлері (болса), `{ORG, TARIFF, DATE, AMOUNT, CHANNEL, ORDER_ID, CONTACT}` жиынынан алынған. Ауыстыру қажет болмаса — бос тізім. |

### Деректер бөлінісі

Датасет қазіргі уақытта **бір бүтін файл** ретінде шығарылған (`dataset_1_.jsonl`, 406 жазба, әр жолда бір JSON объектісі, UTF-8). Ресми train/validation/test бөлінісі берілмеген. Классификация тапсырмаларын бенчмарктейтін пайдаланушыларға өз стратификацияланған бөлінісін жасау ұсынылады (мысалы, `domain` бойынша), және қайталанатын салыстырулар үшін тұрақты тест бөлігін бөліп қою ұсынылады.

- Жалпы жазба саны: **406**
- Ағымдағы шығарылымда қайталанатын сұрақтар мен жауаптар табылмады.
- Барлық жазбалардың `id`-і бірегей.

---

## Датасетті құрастыру

### Құрастыру негіздемесі

Датасет ағылшын немесе орыс тілдерімен салыстырғанда сирек кездесетін **қазақ тіліндегі, пәндік салаға бағытталған диалогтық деректердің** ашық жетіспеушілігін толтыру үшін құрастырылды. Ол клиенттерге қолдау көрсету сценарийлеріне бағытталған, себебі бұл қазақ тілінде сөйлейтін көмекшілерді нақты бизнестерде (банктер, телеком операторлары, бөлшек сауда қызмет орталықтары) енгізу үшін құнды әрі шектеулі қолданылу аймағы, әрі жариялауға қауіпсіз (нақты жеке немесе ұйымдық деректер жоқ — сезімтал өрістер `{{PLACEHOLDER}}` слоттарына абстракцияланған).

### Дереккөз

Жауаптар нақты қолдау көрсету транскрипттерінен алынбаған сияқты — қолдан/үлгі бойынша жазылған (қысқа, жалпы, саясатқа сай тұжырымдама; тұрақты стиль; нақты веб-контент жоқ) көрінеді.

### Жеке және сезімтал ақпарат

Датасетте нақты жеке деректер жоқ сияқты. Ұйым атаулары, нақты тарифтер, күндер, сомалар мен байланыс деректері нақты нысандарға сілтеме жасамай, әдейі плейсхолдер белгілеріне (`{{ORG}}`, `{{TARIFF}}` және т.б.) абстракцияланған.

---

## Деректерді пайдалану бойынша ескертулер

### Шектеулер

- **Шағын көлем** (406 жазба) — few-shot промпттеу, жеңіл instruction-tuning немесе бағалау үшін жеткілікті, бірақ модельді нөлден оқыту үшін жалғыз өзі жеткіліксіз.
- **Әр интентке бір ғана мысал** — `intent` өрісі аугментация/парафраз кеңейтусіз әдеттегі оқытылатын классификация белгілер жиынтығы ретінде дайын күйінде пайдаланылмайды.
- **Домендердің теңгерімсіздігі** — `banking` (34.7%) `billing`-пен (3.9%) салыстырғанда айтарлықтай басым; оқыту/бағалау кезінде стратификация немесе қайта салмақтау қажет.
- **Үлгілік стиль** — жауаптар тұрақты, біршама формалды "жалпы қолдау агенті" стилін ұстанады; тек осы деректермен оқытылған модельдер нақты пайдаланушылардың бейресми немесе эмоционалды хабарламаларына толық жалпыланбауы мүмкін.
- **Плейсхолдерлерді кейін шешу қажет** — осы деректермен оқытылған кез келген жүйе `{{ORG}}`/`{{TARIFF}}` және т.б. нақты мәндермен ауыстыру логикасын бөлек іске асыруы немесе оларды үлгілеу қабаты үшін нақты сақтауы керек.

### Ұсынылатын қолданыстар
- Қолдау боттары үшін қазақ тіліндегі instruction-tuning / SFT деректерін толықтыру.
- Қазақ LLM-дерін бағалау үшін few-shot промпттеу үлгі жиынтығы.
- LLM-дердің қазақша жатықтығын, галлюцинациядан аулақ болуын және домен/субдомен классификациясын бенчмарктеу.

---

## Лицензия туралы ақпарат

- **Осы жария үлгі (406 жазба): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)** — кез келген адам, кез келген мақсатта, **соның ішінде коммерциялық мақсатта да** (fine-tuning, өнімдер, зерттеу, қайта тарату және т.б.) тегін пайдалана алады, **тек түпнұсқа авторы/ұйымы (Mäñgi ÜTM / `mangi-llm`) көрсетілу шартымен**.
- **Толық датасет (~10 000 жұп):** Осы лицензия аясында жария етілмеген. Бұл үлгі толық жинақтың бір бөлігі ғана. Толық датасетке қолжетімділік алу үшін шарттарды талқылау мақсатында **kurumikaz@gmail.com** мекенжайына хабарласыңыз — толық нұсқа **бөлек, ақылы лицензиямен** ұсынылады деп күтілуде.
- Датасетті пайдаланған кезде `mangi-llm`-ге / осы датасет репозиторийіне сілтейтін дәйексөз немесе атрибуция жолын қосыңыз (қараңыз: [Дәйексөз](#дәйексөз-ақпараты)).

## Дәйексөз ақпараты

```
@misc{kazakh_customer_support_qa,
  title = {kazakh-customer-support-qa},
  author = {Mäñgi ÜTM (mangi-llm community)},
  year = {2025},
  howpublished = {\url{https://huggingface.co/mangi-llm}}
}
```

## Құрастырушы ұйым туралы

**Mäñgi ÜTM** (`mangi-llm`) — қазақ тіліндегі ірі тілдік модельдерге қызығатын ашық қауымдастық. Ол қазақи датасеттерді жинайды және бөліседі, мақсаты — ұйымның өз сипаттамасында айтылғандай, қазақ тілін сандық кеңістікте мәңгілеу.