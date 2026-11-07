"""Rubric-conditional examples; authored here, no DEV labels or transcripts."""
VERSION = 'cqa-decision-guided-v1'
GUIDANCE = '''
Before EACH decision, check the criterion's applicability condition against the dialogue.
Distinguish: action NOT REQUIRED => not_applicable when allowed; required but NOT DONE => no.
Examples below explain reasoning patterns ONLY. The supplied rubric overrides every example.
- If identity verification is required only for protected actions and N/A covers public advice:
  client asks a public tariff question, operator gives public information => not_applicable.
  Do NOT answer no merely because identity was not checked; it was not required.
- If need discovery is N/A when all details were already known: client gives a complete request,
  operator immediately answers => not_applicable. A useful recommendation is not a question.
- If closing requires (recap OR offer of more help) AND farewell: operator only says goodbye
  => no. Client saying thanks or confirming resolution is NOT an operator recap.
  An earlier substantive answer is not an extra concluding recap.
- If N/A is not allowed, never use it. Missing evidence required to establish a fact may mean
  needs_review rather than yes or no; insufficient evidence is different from not applicable.
- For a violation flag, yes means the prohibited EVENT occurred. Check the actual actor and action.
  Client insults do not prove operator insults. A failed identity check alone is not disclosure;
  disclosing a specific private account fact without verification may be disclosure under the rubric.
  An offer of private paid advice bypassing the company is an event even without client acceptance,
  if the rubric says so. An official company service is not automatically a private paid service.
Keep explanations consistent with the chosen answer. 'Not required' must not be encoded as yes/no
when the rubric explicitly requires not_applicable for that situation.
'''
