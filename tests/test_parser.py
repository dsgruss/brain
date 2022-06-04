from brain.interfaces import HeldInputJack, LocalState
from brain.parsers import Halt, MessageParser, PatchConnection, SnapshotRequest, SnapshotResponse, Update

def test_halt():
    m = MessageParser()
    msg = Halt("GLOBAL")
    assert msg == m.parse_directive(m.create_directive(msg))

def test_update():
    m = MessageParser()
    msg = Update("testuuid", LocalState([HeldInputJack("testuuid", "1")], []))
    print(m.create_directive(msg))
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))

def test_snapshotrequest():
    m = MessageParser()
    msg = SnapshotRequest("testuuid")
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))

def test_snapshotresponse():
    m = MessageParser()
    msg = SnapshotResponse("testuuid", b"123912378123", [])
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))

def test_snapshotresponse():
    m = MessageParser()
    msg = SnapshotResponse(
        "testuuid", b"123912378123", [PatchConnection("testuuid", 2, "testuuid2", "1")]
    )
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))