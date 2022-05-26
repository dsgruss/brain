from brain.interfaces import HeldInputJack, LocalState
from brain.parsers import Message, MessageParser, MessageType

def test_halt():
    m = MessageParser()
    msg = Message("GLOBAL", MessageType.HALT)
    assert msg == m.parse_directive(m.create_directive(msg))

def test_update():
    m = MessageParser()
    msg = Message("testuuid", MessageType.UPDATE, LocalState([HeldInputJack("testuuid", "1")], []))
    print(m.create_directive(msg))
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))