"""PaperPath의 모든 정규표현식 규칙.

규칙의 실체(패턴)와 설명(잡는 것, 예시, 일부러 놓치는 경우, 화면에 보일 한국어 이유)을
이 파일 한 곳에 모은다. 탐색 알고리즘(약어 글자 맞추기, 뼈대 선택)은 extract.py가 맡는다.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    """화면과 규칙 탐색 탭에 노출되는 규칙 하나."""

    name: str
    category: str          # abbr / hedge / confident / reference / problem / method / result / limit / clean / split
    label: str             # 화면 표시 이름
    pattern: re.Pattern
    desc: str              # 무엇을 잡는가
    reason: str = ""       # 뼈대 카드·툴팁에 붙는 한국어 이유 한 줄
    examples: tuple = field(default_factory=tuple)   # 잡는 예
    misses: tuple = field(default_factory=tuple)     # 일부러 놓치는 경우
    toggleable: bool = False


# ====================================================================== 전처리 (P0-1 최소 방어선)

SOFT_NEWLINE = re.compile(r"(?<!\n)[ \t]*\n[ \t]*(?!\n)")
"""문단 안의 한 줄 개행 → 공백. 빈 줄(문단 경계)은 남긴다."""

MULTI_SPACE = re.compile(r"[ \t]{2,}")
"""연속 공백 → 공백 하나."""

DEHYPHEN = re.compile(r"(?<=[a-z])-[ \t]*\n[ \t]*(?=[a-z])")
"""줄 끝 하이픈으로 끊긴 단어 복원: ``termi-\\nnology`` → ``terminology``.

일부러 놓치는 경우: ``state-of-\\nthe-art``처럼 원래 하이픈이 있던 단어는 붙어 버린다.
"""

PAGE_NUMBER_LINE = re.compile(r"^[ \t]*\d{1,4}[ \t]*$", re.M)
"""숫자만 있는 줄(쪽번호) 제거."""

HEADER_MAX_LEN = 60
HEADER_MIN_REPEAT = 3
"""같은 짧은 줄(60자 이하)이 3번 이상 나오면 머리말로 보고 제거한다(줄 세기는 clean.py)."""

# ====================================================================== 문장 분리 (P0-1)

SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\"'])|\n{2,}")
"""문장 경계: 마침표·물음표·느낌표 뒤 공백 + 대문자/여는 괄호, 또는 빈 줄."""

NON_FINAL = re.compile(
    r"(?:\b(?:e\.g|i\.e|et al|vs|Figs?|Eqs?|Secs?|cf|approx|ca|Refs?|resp|No|Dr|Mr|Mrs|Ms|Prof|St)"
    r"|\bU\.S|\bU\.K)\.$",
    re.I,
)
"""마침표가 있어도 문장 끝이 아닌 약어. 경계 직전 텍스트가 이 패턴으로 끝나면 자르지 않는다.

일부러 놓치는 경우: 목록에 없는 약어 뒤에 대문자가 오면 잘린다.
"""

MATH = re.compile(r"\$[^$\n]{1,120}\$|\\\(.+?\\\)")
"""인라인 수식 ``$...$``, ``\\( ... \\)``. 문장 분리 전에 가려서 수식 안 마침표에서 자르지 않는다."""

URL = re.compile(r"https?://\S+")

# ====================================================================== 약어 (P0-3)

ACRONYM_CANDIDATE = re.compile(
    r"\(\s*(?P<abbr>(?=(?:[^A-Z)]*[A-Z]){2})[A-Za-z][A-Za-z0-9-]{1,11})\s*\)"
)
"""괄호 안 약어 후보: 대문자가 2개 이상인 2~12자 토큰. ``(NLP)``, ``(LLMs)``, ``(LoRA)``, ``(CoT)``.

후보만 찾는다. 앞 단어와 글자를 맞추는 일은 extract.match_long_form()이 한다.
"""

LINKER_WORDS = frozenset({"of", "from", "and", "the", "for", "in", "on", "with", "to", "a", "an", "by", "via"})
"""풀네임 안에 끼어도 되는 연결어(약어 글자를 맡지 않음)."""

WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*")
"""풀네임 후보를 이루는 단어(하이픈 단어는 한 덩어리)."""

BARE_ACRONYM = re.compile(r"\b[A-Z][A-Za-z]*[A-Z][A-Za-z0-9]*s?\b")
"""정의 없이 쓰인 대문자 약어 후보: ``GPU``, ``GPT``.

대문자 비율이 BARE_MIN_UPPER_RATIO 미만이면 약어로 보지 않는다(extract.py). ``REasoning``처럼
강조용으로 앞 두 글자만 대문자인 단어를 거르기 위해서다(``XGBoost`` 0.43은 통과).
"""

BARE_MIN_UPPER_RATIO = 0.4

ABBR_RULE = Rule(
    "ABBR", "abbr", "약어",
    ACRONYM_CANDIDATE,
    "괄호 안 약어 후보를 찾고, 앞 단어 첫 글자와 순서대로 맞춰 풀네임을 붙인다. 대문자로 맞추기에 실패하면 약어의 모든 글자로 한 번 더 맞춘다.",
    reason="괄호 안 약어를 앞 단어 첫 글자와 맞춰 풀네임을 찾았어요",
    examples=("Gated Recurrent Unit (GRU)", "Low-Rank Adaptation (LoRA)", "Chain-of-Thought (CoT)"),
    misses=("Extreme Gradient Boosting (XGBoost)", "Bidirectional LSTM (BiLSTM)", "k-nearest neighbors (k-NN)"),
    toggleable=True,
)

# ====================================================================== 추측·확신·참조 (P0-4)

HEDGE = re.compile(
    r"\b(?:may|might|could)\b"
    r"|\b(?:suggests?|suggesting|indicates?|likely|unlikely|possibly|perhaps|potentially|presumably)\b"
    r"|\b(?:appears?|seems?|tends?)\s+to\b",
    re.I,
)
HEDGE_EXCLUDE = re.compile(
    r"\b(?:may|can|could|might)\s+(?:(?:also|not|\w+ly)\s+){0,2}be\s+(?:\w+ly\s+)?"
    r"(?:applied|used|extended|adapted|employed|deployed|integrated|combined)\b",
    re.I,
)

HEDGE_RULE = Rule(
    "HEDGE", "hedge", "추측·가능성",
    HEDGE,
    "주장의 강도를 낮추는 조동사·인식 표현. 3등급으로 나누지 않고 한 등급으로 표시한다.",
    reason="저자가 단정하지 않는 표현이에요. 인용할 때 '~일 수 있다'로 옮기세요",
    examples=("may not necessarily reflect", "These findings suggest", "seems to"),
    misses=("문장을 넘는 문맥", "may 뒤 동사의 뜻(조동사 자체를 표시)"),
    toggleable=True,
)
HEDGE_EXCLUDE_RULE = Rule(
    "HEDGE_EXCLUDE", "hedge", "추측 제외(가능·허용)",
    HEDGE_EXCLUDE,
    "'~에 적용될 수 있다'처럼 가능·허용 뜻의 조동사는 추측으로 칠하지 않는다. 사이에 부사·부정어가 2개까지 끼어도 잡는다.",
    reason="가능·허용 뜻이라 추측 표시에서 뺐어요",
    examples=("may be applied", "could also be easily extended"),
    misses=("목록에 없는 동사(be evaluated 등)",),
    toggleable=True,
)

CONFIDENT = re.compile(
    r"\b(?:demonstrat(?:e|es|ed|ing)|clearly|significantly|substantially|dramatically|consistently"
    r"|prove[sdn]?|confirm(?:s|ed)?|undoubtedly|state[- ]of[- ]the[- ]art|outperform(?:s|ed|ing)?"
    r"|remarkabl[ey]|superior)\b",
    re.I,
)
CONFIDENT_RULE = Rule(
    "CONFIDENT", "confident", "확신",
    CONFIDENT,
    "결과를 강하게 주장하는 표현.",
    reason="저자가 강하게 주장하는 표현이에요. 근거(수치·표)를 함께 확인하세요",
    examples=("significantly improves", "We demonstrate", "state-of-the-art"),
    misses=("통계적 유의성과 단순 강조의 구분",),
    toggleable=True,
)

CITE_NUM = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")
CITE_AUTHOR = re.compile(
    r"\((?:e\.g\.,?\s*)?[A-Z][A-Za-z'-]+(?:\s+et al\.|\s+(?:and|&)\s+[A-Z][A-Za-z'-]+)?,?\s+\d{4}[a-z]?"
    r"(?:;\s*[A-Z][A-Za-z'-]+(?:\s+et al\.|\s+(?:and|&)\s+[A-Z][A-Za-z'-]+)?,?\s+\d{4}[a-z]?)*\)"
)
XREF = re.compile(
    r"\b(?:Fig(?:ure)?s?|Tables?|Eqs?|Equations?|Sec(?:tion)?s?|Appendix|Alg(?:orithm)?)\.?\s*(?:\(\d+\)|[A-Z]?\d+(?:\.\d+)*)"
)
REFERENCE = re.compile(f"{CITE_NUM.pattern}|{CITE_AUTHOR.pattern}|{XREF.pattern}")
REFERENCE_RULE = Rule(
    "REFERENCE", "reference", "참조",
    REFERENCE,
    "번호식 인용 [12], 저자-연도 인용 (Smith et al., 2020), 그림·표·수식·절 참조 Fig. 3 / Table 2 / Eq. (4).",
    reason="다른 논문이나 그림·표를 가리키는 표시예요",
    examples=("[4]", "(Smith et al., 2021)", "Table 2", "Eq. (4)"),
    misses=("각주형 인용",),
    toggleable=True,
)

TOKEN_RULES = (ABBR_RULE, HEDGE_RULE, HEDGE_EXCLUDE_RULE, CONFIDENT_RULE, REFERENCE_RULE)

# ====================================================================== 3줄 뼈대 (P0-2)

SK_PROBLEM = re.compile(
    r"\A\s*(?:but|yet)\b"
    r"|\b(?:however|despite|although|unfortunately|challeng(?:e|es|ing)"
    r"|remains? (?:an? )?(?:open|unclear|difficult|unsolved)"
    r"|(?:key|major|main|central) (?:problem|issue|limitation|bottleneck)s?"
    r"|little (?:is known|attention|work)|lack(?:s|ing)? (?:of )?|struggles? to|suffer(?:s)? from"
    r"|is (?:costly|expensive|time-consuming)|existing (?:methods|approaches|work))\b",
    re.I,
)
SK_METHOD = re.compile(
    r"\b(?:in this (?:paper|work|study|article),? we"
    r"|we (?:propose|present|introduce|develop|design|describe|investigate|study)"
    r"|our (?:approach|method|model|framework|system|technique)"
    r"|this (?:paper|work) (?:proposes|presents|introduces))\b",
    re.I,
)
SK_RESULT = re.compile(
    r"\b(?:results? (?:show|indicate|demonstrate|suggest|reveal)|we (?:find|found|show|observe|demonstrate)"
    r"|experiments?\b[^.]{0,60}?\b(?:show|demonstrate|reveal)s?|outperform\w*"
    r"|achiev\w* (?:an? )?(?:new )?(?:state[- ]of[- ]the[- ]art|improvement|accuracy|f1|bleu)"
    r"|improv\w* (?:by|over|upon))\b"
    r"|\d+(?:\.\d+)?\s?%",
    re.I,
)
SK_LIMIT = re.compile(
    r"\b(?:limitations?|future (?:work|research|directions?)|(?:does|do) not (?:generalize|address|consider)"
    r"|remains? to be|we leave|is limited to|only (?:applies|works)|broader impacts?|ethic(?:s|al|ally)"
    r"|open (?:question|problem)s?)\b",
    re.I,
)

SKELETON_RULES = (
    Rule("SK_PROBLEM", "problem", "문제 · Problem", SK_PROBLEM,
         "연구가 다루는 어려움·빈틈을 밝히는 신호 문구. 대조어(but, despite, although 등)도 포함한다.",
         reason="어려움을 직접 밝혀 연구 문제를 나타내는 표현",
         examples=("remains challenging", "However, ...", "existing methods struggle to")),
    Rule("SK_METHOD", "method", "방법 · Method", SK_METHOD,
         "저자가 한 일(제안 방법)을 알리는 신호 문구.",
         reason="새로운 접근법을 제안하는 방법 신호",
         examples=("we introduce", "In this paper, we", "our framework")),
    Rule("SK_RESULT", "result", "결과 · Result", SK_RESULT,
         "실험이 보여 준 것을 알리는 신호 문구와 수치.",
         reason="실험 결과를 알리는 표현이 포함된 문장",
         examples=("Experiments ... show", "outperforms", "by 8.4%")),
    Rule("SK_LIMIT", "limit", "한계", SK_LIMIT,
         "한계·향후 과제·윤리 문장. 3줄 뼈대의 결과 대체 후보에서 빼고 한계 후보로 보낸다.",
         reason="한계나 향후 과제를 밝히는 문장",
         examples=("future work", "we leave ... for", "broader impact")),
)

PUBLIC_RELEASE = re.compile(
    r"https?://|github"
    r"|\b(?:code|data(?:set)?s?|models?|resources?)\b[^.]{0,40}\b(?:is|are|will be)\s+"
    r"(?:publicly\s+|made\s+|freely\s+)?(?:available|released)"
    r"|\bwe (?:release|make)\b",
    re.I,
)
"""코드·데이터 공개 문장. 3줄 뼈대의 대체 문장으로 고르지 않는다."""

AUTHOR_VOICE = re.compile(r"\b(?:we|our)\b", re.I)
"""방법 대체: 'we/our'가 들어간 첫 문장."""

RESULT_HINT = re.compile(r"\d|\b(?:improv|achiev|outperform|reduc|increas|show|reveal|find|found|yield)\w*", re.I)
"""결과 대체: 수치나 결과 동사가 있는 문장을 우선한다."""

POSITION_FALLBACK_RULE = Rule(
    "SK_FALLBACK", "skeleton", "뼈대 위치 대체",
    AUTHOR_VOICE,
    "신호 문구가 없을 때만 위치로 대체한다. 문제 = 첫 문장('분야 배경 (첫 문장)'), "
    "방법 = we/our가 든 첫 문장, 결과 = 공개·한계 문장을 뺀 뒤쪽 문장 중 수치·결과 동사가 있는 문장.",
    reason="신호 문구가 없어 위치로 골랐어요(추정)",
    toggleable=True,
)

TOGGLEABLE_RULES = tuple(r for r in (*TOKEN_RULES, POSITION_FALLBACK_RULE) if r.toggleable)
DEFAULT_ACTIVE_RULES = frozenset(r.name for r in TOGGLEABLE_RULES)

# ====================================================================== 번역 보호·후처리 (P0-5)

NUMBER = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?:\s?%|x\b)?")
"""수치: ``8.4%``, ``1,000``, ``3x``. 번역 보호에는 쓰지 않는다(아래 참고)."""

PROTECT_PATTERNS = (URL, MATH, CITE_NUM, CITE_AUTHOR, XREF)
"""번역에서 보호할 토큰(앞에 있을수록 우선). 약어는 문서마다 달라서 translate.py가 앞에 붙인다.

수치(NUMBER)는 2026-11-04 마스킹 30편 실측 뒤 뺐다. 수치를 <x>로 가리자 DeepL이 한 문장 안의
'우리 방법 72.3%'와 '기존 방법 67.9%'를 구분하지 못하고 앞 수치를 두 번 써서 틀린 숫자를 만들었다
(1812.10896). 마스킹을 끄면 수치는 '2,000', '1,000만'처럼 표기만 바뀌고 값은 맞았다.
"""

X_TAG = re.compile(r"</?x>")
SENT_TAG = re.compile(r"<s>(.*?)</s>", re.S)
"""문단 번역에서 문장 짝을 복원하는 태그."""

KO_JE_BEFORE_REF = re.compile(r"제\s?(?=(?:Sec(?:tion)?|Table|Fig(?:ure)?|Eq|Appendix|Alg)\b)")
"""DeepL이 보호된 참조 앞에 붙이는 '제'(예: '제Section 5.1') 제거."""

KO_PARTICLE_SPACE = re.compile(r"(?<=[A-Za-z0-9%)\]])[ \t]+(?=(?:은|는|가|을|를|의|에|와|과|도|로)(?=[\s.,)]|$))")
"""영문·숫자·괄호 뒤의 공백 + 조사 → 공백 제거. '이'는 지시어('이 방법')와 겹쳐 목록에서 뺐다."""

KO_SPACE_BEFORE_CITE = re.compile(r"(?<=[가-힣])[ \t]+(?=\[\d)")
"""한국어 뒤 번호식 인용 앞 공백 제거: '수 있다 [4]' → '수 있다[4]'."""

# ====================================================================== 입력 (collect)

ARXIV_ID = re.compile(
    r"^\s*(?:arxiv:\s*)?(?P<id>(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v\d+)?)\s*$",
    re.I,
)
"""arXiv ID: 새 형식 ``2402.08910``(``v2``, ``arXiv:`` 접두 허용), 옛 형식 ``cs/0112017``."""
