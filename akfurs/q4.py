"""Q4. Чаты, где менеджер пригласил на встречу/примерку раньше, чем назвал цену."""
import re
from dataclasses import dataclass

from .chats import MANAGER
from .io_utils import warn
from .money_text import find_amounts

# Приглашение — призыв приехать / записаться, а не справка об адресе шоурума
# («Шоурум расположен в центре…») и не реплики клиента («загляну в пятницу»).
INVITE_RE = re.compile(
    r"приглаша|приезжа|подъезжа|подъех|приех|приед|загляни|зайдите|приходите"
    r"|запиш[а-яё]*\s+вас|записать\s+вас|жд[её]м\s+вас|на\s+примерк|на\s+встреч",
    re.IGNORECASE,
)
# слова о цене: если сумма в таком сообщении не найдена, стоит проверить вручную
PRICE_WORDS_RE = re.compile(r"цен[аеуы]|стоимост|руб|₽|тыс|млн|миллион", re.IGNORECASE)


@dataclass
class Verdict:
    chat_id: str
    first_price: int | None   # индекс сообщения менеджера с первой суммой
    first_invite: int | None  # индекс первого приглашения от менеджера

    @property
    def invite_before_price(self):
        """Приглашение есть, а цена названа позже или не названа вовсе.

        Если цена и приглашение в одном сообщении — цена названа не позже, нарушения нет.
        """
        if self.first_invite is None:
            return False
        return self.first_price is None or self.first_invite < self.first_price


def is_price(text):
    return bool(find_amounts(text))


def is_invite(text):
    return bool(INVITE_RE.search(text))


def judge(chat):
    first_price = first_invite = None
    for i, msg in enumerate(chat.messages):
        if msg.speaker != MANAGER:
            continue  # суммы и «загляну» от клиента не считаются
        price, invite = is_price(msg.text), is_invite(msg.text)
        if not price and PRICE_WORDS_RE.search(msg.text):
            warn(f"Чат {chat.chat_id}: похоже на цену, но сумма не распознана: '{msg.text}'")
        if price and first_price is None:
            first_price = i
        if invite and first_invite is None:
            first_invite = i
    return Verdict(chat.chat_id, first_price, first_invite)


def solve(chats):
    verdicts = [judge(c) for c in chats]
    return {"q4_chats_meeting_before_price": sorted(v.chat_id for v in verdicts
                                                    if v.invite_before_price)}
