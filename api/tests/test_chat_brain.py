from datetime import date

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
