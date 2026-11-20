"""Store cash notes outside the immutable audit payload; verify them on read."""
import hmac
from cryptography.exceptions import InvalidTag
from api.app import security as sec
from api.app.services.receivables import seal, unseal


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS cash_notes(
      business_id TEXT NOT NULL, source_id TEXT NOT NULL, ciphertext TEXT NOT NULL,
      PRIMARY KEY(business_id,source_id),
      FOREIGN KEY(business_id,source_id) REFERENCES source_records(business_id,source_record_id))""")


def store(db, business, source, kind, note):
    if not note:
        return {}
    signature = sec.signature('private-record-note', [business,source,note])
    if kind == 'event':
        key = bytes.fromhex(sec.signature('cash-note-encryption-v1', business))
        db.execute('INSERT INTO cash_notes VALUES (?,?,?)', (business,source,seal(key,note.encode(),source)))
    return {'note_hash':signature}


def read(db, business, audit):
    entries = [event['payload'] for event in audit if event['kind']=='RECORD_ADDED']
    notes = {entry['source_id']:entry['note'] for entry in entries if entry.get('note')}
    expected = {entry['source_id']:entry['note_hash'] for entry in entries if entry.get('note_hash') and entry['kind']=='event'}
    if not expected:
        return notes
    key = bytes.fromhex(sec.signature('cash-note-encryption-v1',business))
    for source, ciphertext in db.execute('SELECT source_id,ciphertext FROM cash_notes WHERE business_id=?',(business,)):
        try:
            note = unseal(key,ciphertext,source).decode()
            digest = expected.pop(source)
            if not hmac.compare_digest(sec.signature('private-record-note',[business,source,note]),digest):
                raise ValueError()
        except (InvalidTag, ValueError, KeyError, UnicodeError):
            sec.fail(409,'RECORD_NOTE_INTEGRITY_FAILURE')
        notes[source] = note
    if expected:
        sec.fail(409,'RECORD_NOTE_INTEGRITY_FAILURE')
    return notes
