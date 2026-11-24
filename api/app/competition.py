"""Public competition walkthrough using fixed, fictional inputs and the real engines."""
from datetime import timedelta

from fastapi import APIRouter

from api.app.accounts import today_bd
from api.app.services import radar
from api.app.services.finance import validated
from api.app.voice_batch import split_note

router = APIRouter(prefix='/api/competition')

NOTE = ('Gotokal dokan bhara 5000 taka dilam. Tarpor transport 300 taka dilam. '
        'Aj Rahim theke 12 hajar taka pelam. Aj biddut bill 1850 taka baki. Karim 2000 taka dey nai.')


def sample_radar(today):
    def day(offset):
        return today + timedelta(days=offset)

    books = validated(dict(
        opening_source_id='sample-opening', opening_on=today, as_of=today, currency='BDT',
        opening_balance_minor=1_500_000, events=[],
        invoices=[dict(source_record_id='sample-bill', invoice_id='sample-bill', vendor_id='sample-supplier',
                       invoice_number='DEMO-01', issued_on=today, due_on=day(5), amount_minor=3_000_000,
                       currency='BDT', status='open', memo='Fictional supplier bill')],
    ))
    habits, overall = radar.habits_from([
        ('sample-customer', day(-40), day(-33)), ('sample-customer', day(-25), day(-16)),
    ])
    scenarios = {
        'habit': radar.expectations([('sample-invoice', 'sample-customer', day(2), 2_500_000)], habits, overall, today),
        'overdue': radar.expectations([('sample-invoice', 'sample-customer', day(-4), 2_500_000)], {}, None, today),
    }
    for items in scenarios.values():
        items[0]['customer'] = 'Karim Traders'
    return {key: radar.outlook(books, 500_000, today, items) for key, items in scenarios.items()}


@router.get('/demo')
def competition_demo():
    today = today_bd()
    drafts, dropped, method = split_note(NOTE, today, 'BDT', 2, use_ai=False)
    return dict(note=NOTE, currency='BDT', voice=dict(drafts=drafts, dropped=dropped, method=method),
                radar=sample_radar(today), simulation_only=True)
