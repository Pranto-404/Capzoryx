from datetime import date
from api.tests.test_accounts import world  # noqa: F401

import pytest

from api.app.chat import brain, understand

# (message, expected topic or small-talk intent, expected language)
CASES = [
    ('cash koto?', 'balance', 'bl'), ('hate koto taka ache', 'balance', 'bl'), ('how much cash do i have', 'balance', 'en'),
    ('whats my balnce', 'balance', 'en'), ('হাতে কত টাকা আছে?', 'balance', 'bn'), ('ব্যালেন্স কত', 'balance', 'bn'),
    ('how much did i earn this month', 'income', 'en'), ('ei mashe bikri koto holo', 'income', 'bl'),
    ('এই মাসে আয় কত?', 'income', 'bn'), ('total sales today', 'income', 'en'), ('revenu last month', 'income', 'en'),
    ('khoroch koto ajke', 'expenses', 'bl'), ('how much did I spend yesterday', 'expenses', 'en'),
    ('গত মাসে খরচ কত', 'expenses', 'bn'), ('expences this week', 'expenses', 'en'),
    ('how much do i owe', 'payables', 'en'), ('supplier der koto dite hobe', 'payables', 'bl'),
    ('কত টাকা দিতে হবে', 'payables', 'bn'), ('any overdue bills?', 'payables', 'en'),
    ('who owes me money', 'receivables', 'en'), ('customer der kache koto paona', 'receivables', 'bl'),
    ('কে কত পাওনা', 'receivables', 'bn'), ('baki koto', 'receivables', 'bl'),
    ('cash forecast next week', 'forecast', 'en'), ('samne cash koto thakbe', 'forecast', 'bl'),
    ('আগামী মাসে কত থাকবে', 'forecast', 'bn'),
    ('how is my business doing', 'summary', 'en'), ('business kemon cholche', 'summary', 'bl'),
    ('ব্যবসার অবস্থা কেমন', 'summary', 'bn'), ('give me a summary', 'summary', 'en'),
    ('hi', 'greet', 'en'), ('assalamu alaikum', 'greet', 'en'), ('হ্যালো', 'greet', 'bn'),
    ('kemon acho', 'how_are_you', 'bl'), ('how are you?', 'how_are_you', 'en'), ('কেমন আছেন', 'how_are_you', 'bn'),
    ('thanks!', 'thanks', 'en'), ('dhonnobad', 'thanks', 'bl'), ('ধন্যবাদ', 'thanks', 'bn'),
    ('who are you', 'who', 'en'), ('tumi ke', 'who', 'bl'), ('what can you do', 'help', 'en'), ('bye', 'bye', 'en'),
    ('ok', 'ack', 'en'), ('thik ache', 'ack', 'bl'),
]


# Misspelt, slang, formal and mixed-script messages real owners send.
NOISY = [
    ('cash kto ase vai', 'balance'), ('hate kot taka ace', 'balance'), ('CASH KOTO??', 'balance'), ('blance ta bolo', 'balance'),
    ('আমার বর্তমান নগদ স্থিতি জানতে চাই', 'balance'), ('Kindly let me know my current cash position', 'balance'),
    ('ei mase khoros koto hoilo', 'expenses'), ('khrch kto', 'expenses'), ('এ মাসে খরচ কেমন হইছে', 'expenses'),
    ('bikri koto hoise aj', 'income'), ('aj koto sell holo', 'income'), ('আজ বিক্রি কত', 'income'),
    ('kar kase koto paona', 'receivables'), ('baki koto ase customer der', 'receivables'),
    ('কাস্টমাররা কত টাকা বাকি রাখছে', 'receivables'), ('supplir k koto dibo', 'payables'), ('dena koto', 'payables'),
    ('মহাজনের দেনা কত', 'payables'), ('samner soptahe ki obostha hobe', 'forecast'), ('next week e cash thakbe?', 'forecast'),
    ('business er obostha ki', 'summary'), ('sob mile hisab dao', 'summary'),
    ('Could you provide an overview of my business?', 'summary'), ('hlw', 'greet'), ('salam vai', 'greet'),
    ('assalamualaikum', 'greet'), ('Good evening', 'greet'), ('শুভ সন্ধ্যা', 'greet'), ('kmn aso', 'how_are_you'),
    ('kemon achen apni', 'how_are_you'), ('ki khobor', 'how_are_you'), ('thnx', 'thanks'), ('dhonnobad vai', 'thanks'),
    ('tumi ke re', 'who'), ('apni ki manush', 'who'), ('ki ki korte paren', 'help'),
]


@pytest.mark.parametrize('message,expected', NOISY)
def test_understands_misspelt_slang_and_formal_messages(message, expected):
    parsed = understand.parse(message)
    assert (parsed.topic or parsed.small_talk) == expected, parsed.scores

@pytest.mark.parametrize('message,expected,lang', CASES)
def test_understands_everyday_money_chat(message, expected, lang):
    parsed = understand.parse(message)
    assert (parsed.topic or parsed.small_talk) == expected, parsed.scores
    assert parsed.lang == lang


def test_modifiers_windows_and_records():
    p = understand.parse('any overdue bills?')
    assert p.overdue and p.topic == 'payables'
    p = understand.parse('who owes me the most?')
    assert p.listing and p.topic == 'receivables'
    assert understand.parse('ei mashe khoroch').window == 'this_month'
    assert understand.parse('গত মাসে আয়').window == 'last_month'
    assert understand.parse('spent yesterday').window == 'yesterday'
    assert understand.parse('Rahim theke 500 taka pelam').record_like
    assert understand.parse('রহিমকে ১২০০ টাকা দিলাম').record_like
    assert not understand.parse('how much did i receive this month').record_like
    assert understand.parse('ha').yes and understand.parse('na').no and understand.parse('হ্যাঁ').yes


def test_typo_tolerance_is_limited_to_one_edit():
    assert understand.near('balnce', 'balance') and understand.near('expenes', 'expenses')
    assert understand.near('khroch', 'khoroch') and not understand.near('bal', 'balance')
    assert not understand.near('balloon', 'balance')


def test_money_reads_like_bangladeshi_owners_write_it():
    assert brain.money(125000000, 'BDT') == '৳12,50,000'
    assert brain.money(389241, 'BDT') == '৳3,892.41'
    assert brain.money(50000, 'BDT', 'bn') == '৳৫০০'
    assert brain.money(-120000, 'USD') == '-USD 1,200'
    assert brain.day_label(date(2026, 11, 24), 'bn') == '২৪ নভেম্বর'


def test_drafts_only_from_verified_complete_cash_phrases():
    class Data:
        opening_on = date(2020, 1, 1)
    draft = brain.make_draft('Rahim theke 500 taka pelam', Data)
    assert draft['amount_minor'] == 50000 and draft['direction'] == 'inflow' and draft['party'] == 'Rahim'
    draft = brain.make_draft('paid 2.5k to Karim Traders yesterday', Data)
    assert draft['amount_minor'] == 250000 and draft['direction'] == 'outflow' and draft['party'] == 'Karim Traders'
    assert brain.make_draft('will pay 500 to Karim tomorrow', Data) is None
    assert brain.make_draft('paid 500 or 600 to Karim', Data) is None


def test_web_chat_answers_members_without_writing(world, monkeypatch):
    from api.tests.test_accounts import signup
    from api.tests.test_bill_email import bill
    c, _ = world
    signup(c, 'webchat_owner')
    bill(c).raise_for_status()
    reply = c.post('/api/chat/message', json={'text': 'supplier der koto dite hobe?'}).json()
    assert reply['understood'] and '৳3,892.41' in reply['text'] and reply['buttons'][0]['payload'] == '__list_payables__'
    reply = c.post('/api/chat/message', json={'text': '__list_payables__'}).json()
    assert '৳3,892.41' in reply['text']
    assert 'Hate cash' in c.post('/api/chat/message', json={'text': 'business kemon cholche'}).json()['text']
    assert not c.post('/api/chat/message', json={'text': 'what is the capital of peru'}).json()['understood']
    reply = c.post('/api/chat/message', json={'text': 'Rahim theke 500 taka pelam'}).json()
    assert not reply['understood'] and not c.get('/api/workspace').json()['events']
